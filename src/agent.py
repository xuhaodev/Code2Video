import re
import argparse
import json
import time
import random
import subprocess
import sys
from typing import List, Dict, Any, Optional, Tuple, Callable
from dataclasses import dataclass
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed, ThreadPoolExecutor

# Add parent directory to path for prompts module
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gpt_request import *
from prompts import *
from utils import *
from scope_refine import *
from external_assets import process_storyboard_with_assets


@dataclass
class Section:
    id: str
    title: str
    lecture_lines: List[str]
    animations: List[Any]  # 可以是字符串或字典
    start_time: str = "00:00"
    end_time: str = "01:00"
    duration_seconds: int = 60
    talk_script: str = ""  # 原始的 content，用于 TTS 和时长参考


@dataclass
class ContentLine:
    text: str
    timestamp: str = None  # 时间戳现在是可选的


@dataclass
class TeachingOutline:
    topic: str
    target_audience: str
    sections: List[Dict[str, Any]]
    total_duration: str = None  # 总时长现在是可选的，由内容决定


@dataclass
class VideoFeedback:
    section_id: str
    video_path: str
    has_issues: bool
    suggested_improvements: List[str]
    raw_response: Optional[str] = None


@dataclass
class RunConfig:
    use_feedback: bool = False
    use_assets: bool = False
    api: Callable = None  # 默认 API（用于 Stage 4 等其他阶段）
    api_stage1: Callable = None  # Stage 1 (Outline) 使用的 API
    api_stage2: Callable = None  # Stage 2 (Storyboard) 使用的 API
    api_stage3: Callable = None  # Stage 3 (Code Generation) 使用的 API
    feedback_rounds: int = 2
    iconfinder_api_key: str = ""
    max_code_token_length: int = 10000
    max_fix_bug_tries: int = 10
    max_regenerate_tries: int = 10
    max_feedback_gen_code_tries: int = 3
    max_mllm_fix_bugs_tries: int = 3
    portrait_mode: bool = True  # 竖屏模式 (9:16 比例，适合手机)
    video_quality: str = "l"  # 视频质量: l(低), m(中), h(高), k(4K)


class TeachingVideoAgent:
    def __init__(
        self,
        idx,
        knowledge_point,
        folder="CASES",
        cfg: Optional[RunConfig] = None,
    ):
        """1. Global parameter"""
        self.learning_topic = knowledge_point
        self.idx = idx
        self.cfg = cfg

        self.use_feedback = cfg.use_feedback
        self.use_assets = cfg.use_assets
        self.API = cfg.api  # 默认 API
        self.API_STAGE1 = cfg.api_stage1 or cfg.api  # Stage 1 API，未指定则用默认
        self.API_STAGE2 = cfg.api_stage2 or cfg.api  # Stage 2 API，未指定则用默认
        self.API_STAGE3 = cfg.api_stage3 or cfg.api  # Stage 3 API，未指定则用默认
        self.feedback_rounds = cfg.feedback_rounds
        self.iconfinder_api_key = cfg.iconfinder_api_key
        self.max_code_token_length = cfg.max_code_token_length
        self.max_fix_bug_tries = cfg.max_fix_bug_tries
        self.max_regenerate_tries = cfg.max_regenerate_tries
        self.max_feedback_gen_code_tries = cfg.max_feedback_gen_code_tries
        self.max_mllm_fix_bugs_tries = cfg.max_mllm_fix_bugs_tries
        self.portrait_mode = cfg.portrait_mode
        self.video_quality = cfg.video_quality

        """2. Path for output"""
        self.folder = folder
        self.output_dir = get_output_dir(idx=idx, knowledge_point=self.learning_topic, base_dir=folder)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.assets_dir = Path(*self.output_dir.parts[: self.output_dir.parts.index("CASES")]) / "assets" / "icon"
        self.assets_dir.mkdir(exist_ok=True)

        """3. ScopeRefine & Anchor Visual"""
        self.scope_refine_fixer = ScopeRefineFixer(api, self.max_code_token_length)
        self.extractor = GridPositionExtractor()

        """4. External Database"""
        knowledge_ref_mapping_path = (
            Path(*self.output_dir.parts[: self.output_dir.parts.index("CASES")]) / "json_files" / "long_video_ref_mapping.json"
        )
        with open(knowledge_ref_mapping_path) as f:
            self.KNOWLEDGE2PATH = json.load(f)
        self.knowledge_ref_img_folder = (
            Path(*self.output_dir.parts[: self.output_dir.parts.index("CASES")]) / "assets" / "reference"
        )
        # 如果 assets/reference 不在 src 下，尝试上一级目录
        if not self.knowledge_ref_img_folder.exists():
            self.knowledge_ref_img_folder = Path(__file__).resolve().parent.parent / "assets" / "reference"
        self.GRID_IMG_PATH = self.knowledge_ref_img_folder / "GRID.png"

        """5. Data structure"""
        self.outline = None
        self.enhanced_storyboard = None
        self.sections = []
        self.section_codes = {}
        self.section_videos = {}
        self.video_feedbacks = {}

        """6. For Efficiency"""
        self.token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

    def _extract_content_from_response(self, response):
        """Extract text content from various API response formats (Gemini, OpenAI, Anthropic)"""
        if response is None:
            return None
        # Try Gemini format
        try:
            return response.candidates[0].content.parts[0].text
        except Exception:
            pass
        # Try OpenAI format
        try:
            return response.choices[0].message.content
        except Exception:
            pass
        # Try Anthropic format
        try:
            return response.content[0].text
        except Exception:
            pass
        # Fallback to string conversion
        return str(response)

    def _request_api_and_track_tokens(self, prompt, max_tokens=10000, api_override=None):
        """packages API requests and automatically accumulates token usage
        
        Args:
            prompt: 请求的 prompt
            max_tokens: 最大 token 数
            api_override: 可选，覆盖默认 API（用于不同阶段使用不同模型）
        """
        api_func = api_override or self.API
        # gpt-51 uses max_completion_tokens instead of max_tokens
        if api_func == request_gpt51_token:
            response, usage = api_func(prompt, max_completion_tokens=max_tokens)
        else:
            response, usage = api_func(prompt, max_tokens=max_tokens)
        if usage:
            self.token_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
            self.token_usage["completion_tokens"] += usage.get("completion_tokens", 0)
            self.token_usage["total_tokens"] += usage.get("total_tokens", 0)
        return response

    def _request_video_api_and_track_tokens(self, prompt, video_path):
        """Wraps video API requests and accumulates token usage automatically"""
        response, usage = request_gemini_video_img(prompt=prompt, video_path=video_path, image_path=self.GRID_IMG_PATH)

        if usage:
            self.token_usage["prompt_tokens"] += usage.get("prompt_tokens", 0)
            self.token_usage["completion_tokens"] += usage.get("completion_tokens", 0)
            self.token_usage["total_tokens"] += usage.get("total_tokens", 0)
        return response

    def get_serializable_state(self):
        """返回可以序列化保存的Agent状态"""
        return {"idx": self.idx, "knowledge_point": self.learning_topic, "folder": self.folder, "cfg": self.cfg}

    def _generate_script_md(self, outline_data: dict):
        """将 outline 中所有 section 的 content 整合成完整讲稿，保存为 script.md"""
        script_file = self.output_dir / "script.md"
        
        topic = outline_data.get("topic", "教学讲稿")
        target_audience = outline_data.get("target_audience", "")
        sections = outline_data.get("sections", [])
        
        script_lines = []
        script_lines.append(f"# {topic}")
        script_lines.append("")
        if target_audience:
            script_lines.append(f"**目标受众**：{target_audience}")
            script_lines.append("")
        script_lines.append("---")
        script_lines.append("")
        
        for section in sections:
            title = section.get("title", "")
            content = section.get("content", "")
            
            # 添加章节标题
            script_lines.append(f"## {title}")
            script_lines.append("")
            
            # 添加内容（兼容字符串和数组格式）
            if isinstance(content, str):
                script_lines.append(content)
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        text = item.get("text", "")
                        script_lines.append(text)
                    else:
                        script_lines.append(str(item))
            script_lines.append("")
        
        # 写入文件
        with open(script_file, "w", encoding="utf-8") as f:
            f.write("\n".join(script_lines))
        
        print(f"📝 Script saved: {script_file}")

    def generate_outline(self) -> TeachingOutline:
        outline_file = self.output_dir / "outline.json"
        script_file = self.output_dir / "script.md"

        if outline_file.exists():
            print("📂 Found outline, loading...")
            with open(outline_file, "r", encoding="utf-8") as f:
                outline_data = json.load(f)
            # 如果 script.md 不存在，则生成
            if not script_file.exists():
                self._generate_script_md(outline_data)
        else:
            """Step 1: Generate teaching outline from topic"""
            refer_img_path = (
                self.knowledge_ref_img_folder / img_name
                if (img_name := self.KNOWLEDGE2PATH.get(self.learning_topic)) is not None
                else None
            )
            prompt1 = get_prompt1_outline(knowledge_point=self.learning_topic, reference_image_path=refer_img_path)

            print(f"📝 Generating Outline...")

            for attempt in range(1, self.max_regenerate_tries + 1):
                # Stage 1: 使用 API_STAGE1
                response = self._request_api_and_track_tokens(prompt1, max_tokens=self.max_code_token_length, api_override=self.API_STAGE1)
                if response is None:
                    print(f"⚠️ Attempt {attempt} failed, retrying...")
                    if attempt == self.max_regenerate_tries:
                        raise ValueError("API requests failed multiple times")
                    continue
                content = self._extract_content_from_response(response)
                print(f"🔍 Raw content (first 500 chars): {content[:500] if content else 'None'}...")
                content = extract_json_from_markdown(content)
                print(f"🔍 After JSON extraction (first 500 chars): {content[:500] if content else 'None'}...")
                try:
                    outline_data = json.loads(content)
                    with open(self.output_dir / "outline.json", "w", encoding="utf-8") as f:
                        json.dump(outline_data, f, ensure_ascii=False, indent=2)
                    break
                except json.JSONDecodeError as e:
                    print(f"⚠️ Outline format invalid on attempt {attempt}: {e}")
                    print(f"⚠️ Content that failed to parse: {content[:1000] if content else 'None'}...")
                    if attempt == self.max_regenerate_tries:
                        raise ValueError("Outline format invalid multiple times, check prompt or API response")

        # 生成 script.md：整合所有 section 的 content 成完整讲稿
        self._generate_script_md(outline_data)

        self.outline = TeachingOutline(
            topic=outline_data["topic"],
            target_audience=outline_data["target_audience"],
            sections=outline_data["sections"],
            total_duration=outline_data.get("total_duration"),
        )
        # 计算实际时长（基于 content 字符数，每5个字符约1秒）
        # 统计所有字符：中文、英文、数学符号、标点等
        total_char_count = 0
        for s in outline_data["sections"]:
            content = s.get("content", "")
            if isinstance(content, str):
                # 统计所有可见字符（去除空白）
                char_count = len(content.replace(" ", "").replace("\n", "").replace("\t", ""))
                total_char_count += char_count
            elif isinstance(content, list):
                # 旧格式：数组，合并所有内容再统计
                for item in content:
                    if isinstance(item, str):
                        total_char_count += len(item.replace(" ", "").replace("\n", "").replace("\t", ""))
        
        # 每5个字符约1秒
        total_estimated_seconds = max(20, total_char_count // 5)
        estimated_duration = f"{total_estimated_seconds // 60}:{total_estimated_seconds % 60:02d}"
        print(f"== Outline generated: {self.outline.topic} ({len(outline_data['sections'])} sections, {total_char_count}字符, 约{estimated_duration})")
        return self.outline

    def generate_storyboard(self) -> List[Section]:
        """Step 2: Generate teaching storyboard from outline (optionally with asset enhancement)"""
        if not self.outline:
            raise ValueError("Outline not generated, please generate outline first")

        storyboard_file = self.output_dir / "storyboard.json"
        enhanced_storyboard_file = self.output_dir / "storyboard_with_assets.json"

        if enhanced_storyboard_file.exists():
            print("📂 Found enhanced storyboard, loading...")
            with open(enhanced_storyboard_file, "r", encoding="utf-8") as f:
                self.enhanced_storyboard = json.load(f)
        elif storyboard_file.exists():
            print("📂 Found storyboard, loading...")
            with open(storyboard_file, "r", encoding="utf-8") as f:
                storyboard_data = json.load(f)
            if self.use_assets:
                self.enhanced_storyboard = self._enhance_storyboard_with_assets(storyboard_data)
            else:
                self.enhanced_storyboard = storyboard_data
        else:
            print("🎬 Generating storyboard...")
            refer_img_path = (
                self.knowledge_ref_img_folder / img_name
                if (img_name := self.KNOWLEDGE2PATH.get(self.learning_topic)) is not None
                else None
            )
            
            # 计算每个 section 的预估时长（基于 content 字符数，每5个字符约1秒）
            outline_with_duration = self.outline.__dict__.copy()
            total_estimated_seconds = 0
            for section in outline_with_duration.get("sections", []):
                content = section.get("content", "")
                if isinstance(content, str):
                    # 统计所有可见字符（去除空白）
                    char_count = len(content.replace(" ", "").replace("\n", "").replace("\t", ""))
                elif isinstance(content, list):
                    # 旧格式：数组，合并所有内容再统计
                    char_count = sum(len(item.replace(" ", "").replace("\n", "").replace("\t", "")) 
                                    for item in content if isinstance(item, str))
                else:
                    char_count = 100  # 默认约20秒
                # 每5个字符约1秒，最少20秒
                estimated_seconds = max(20, char_count // 5)
                section["estimated_duration_seconds"] = estimated_seconds
                section["char_count"] = char_count  # 保存字符数供后续使用
                total_estimated_seconds += estimated_seconds
            
            # 检查总时长是否超过10分钟（600秒），如果超过则按比例压缩
            max_total_seconds = 600
            if total_estimated_seconds > max_total_seconds:
                scale_factor = max_total_seconds / total_estimated_seconds
                for section in outline_with_duration.get("sections", []):
                    section["estimated_duration_seconds"] = int(section["estimated_duration_seconds"] * scale_factor)

            prompt2 = get_prompt2_storyboard(
                outline=json.dumps(outline_with_duration, ensure_ascii=False, indent=2),
                reference_image_path=refer_img_path,
            )

            for attempt in range(1, self.max_regenerate_tries + 1):
                # Stage 2: 使用 API_STAGE2
                response = self._request_api_and_track_tokens(prompt2, max_tokens=self.max_code_token_length, api_override=self.API_STAGE2)
                if response is None:
                    print(f"⚠️ Outline format invalid on attempt {attempt}, retrying...")
                    if attempt == self.max_regenerate_tries:
                        raise ValueError("API requests failed multiple times")
                    continue

                content = self._extract_content_from_response(response)

                try:
                    json_str = extract_json_from_markdown(content)
                    storyboard_data = json.loads(json_str)

                    # Save original storyboard
                    with open(storyboard_file, "w", encoding="utf-8") as f:
                        json.dump(storyboard_data, f, ensure_ascii=False, indent=2)

                    # Enhance storyboard (add assets)
                    if self.use_assets:
                        self.enhanced_storyboard = self._enhance_storyboard_with_assets(storyboard_data)
                    else:
                        self.enhanced_storyboard = storyboard_data
                    break

                except json.JSONDecodeError:
                    print(f"⚠️ Storyboard format invalid on attempt {attempt}, retrying...")
                    if attempt == self.max_regenerate_tries:
                        raise ValueError("Storyboard format invalid multiple times, check prompt or API response")

        # Parse into Section objects (using enhanced storyboard)
        self.sections = []
        
        # 创建 outline section id 到 content 的映射
        outline_content_map = {}
        if self.outline and hasattr(self.outline, 'sections'):
            for outline_section in self.outline.sections:
                section_id = outline_section.get('id', '')
                content = outline_section.get('content', '')
                if isinstance(content, list):
                    content = ' '.join(str(item) for item in content)
                outline_content_map[section_id] = content
        
        for section_data in self.enhanced_storyboard["sections"]:
            # 计算 section 时长（秒）
            duration_seconds = section_data.get("duration_seconds", 60)
            if not duration_seconds and "start_time" in section_data and "end_time" in section_data:
                # 从 start_time 和 end_time 计算
                try:
                    start_parts = section_data["start_time"].split(":")
                    end_parts = section_data["end_time"].split(":")
                    start_secs = int(start_parts[0]) * 60 + int(start_parts[1])
                    end_secs = int(end_parts[0]) * 60 + int(end_parts[1])
                    duration_seconds = end_secs - start_secs
                except:
                    duration_seconds = 60
            
            # 获取对应的 talk_script (content)
            section_id = section_data["id"]
            talk_script = outline_content_map.get(section_id, "")
            
            section = Section(
                id=section_data["id"],
                title=section_data["title"],
                lecture_lines=section_data.get("lecture_lines", []),
                animations=section_data["animations"],
                start_time=section_data.get("start_time", "00:00"),
                end_time=section_data.get("end_time", "01:00"),
                duration_seconds=duration_seconds if duration_seconds else 60,
                talk_script=talk_script,
            )
            self.sections.append(section)

        print(f"== Storyboard processed, {len(self.sections)} sections generated")
        return self.sections

    def _enhance_storyboard_with_assets(self, storyboard_data: dict) -> dict:
        """Enhance storyboard: smart analysis and download assets"""
        print("🤖 Enhancing storyboard: smart analysis and download assets...")

        try:
            enhanced_storyboard = process_storyboard_with_assets(
                storyboard=storyboard_data,
                api_function=self.API,
                assets_dir=str(self.assets_dir),
                iconfinder_api_key=self.iconfinder_api_key,
            )
            enhanced_storyboard_file = self.output_dir / "storyboard_with_assets.json"
            with open(enhanced_storyboard_file, "w", encoding="utf-8") as f:
                json.dump(enhanced_storyboard, f, ensure_ascii=False, indent=2)
            print("✅ Storyboard enhanced with assets")
            return enhanced_storyboard

        except Exception as e:
            print(f"⚠️ Asset download failed, using original storyboard: {e}")
            return storyboard_data

    def generate_section_code(self, section: Section, attempt: int = 1, feedback_improvements=None) -> str:
        """Generate Manim code for a single section"""
        code_file = self.output_dir / f"{section.id}.py"

        if attempt == 1 and code_file.exists() and not feedback_improvements:
            print(f"📂 Found existing code for {section.id}, reading...")
            with open(code_file, "r", encoding="utf-8") as f:
                code = f.read()
                self.section_codes[section.id] = code
                return code
        # print(f"💻 Generating Manim code for {section.id} (attempt {attempt}/{self.max_regenerate_tries})...")
        regenerate_note = ""
        if attempt > 1:
            regenerate_note = get_regenerate_note(attempt, MAX_REGENERATE_TRIES=self.max_regenerate_tries)

        # Add MLLM feedback and improvement suggestions
        if feedback_improvements:
            current_code = self.section_codes.get(section.id, "")
            try:
                modifier = GridCodeModifier(current_code)
                modified_code = modifier.parse_feedback_and_modify(feedback_improvements)
                with open(code_file, "w", encoding="utf-8") as f:
                    f.write(modified_code)

                self.section_codes[section.id] = modified_code
                return modified_code
            except Exception as e:
                print(f"⚠️ GridCodeModifier failed, falling back to original code: {e}")
                code_gen_prompt = get_feedback_improve_code(
                    feedback=get_feedback_list_prefix(feedback_improvements), code=current_code
                )

        else:
            code_gen_prompt = get_prompt3_code(regenerate_note=regenerate_note, section=section, base_class=base_class)

        # Stage 3: 使用 API_STAGE3
        response = self._request_api_and_track_tokens(code_gen_prompt, max_tokens=self.max_code_token_length, api_override=self.API_STAGE3)
        if response is None:
            print(f"❌ Failed to generate code for {section.id} via API call.")
            return ""

        code = self._extract_content_from_response(response)
        if "```python" in code:
            code = code.split("```python")[1].split("```")[0].strip()
        elif "```" in code:
            code = code.split("```")[1].strip()

        # Replace base class
        code = replace_base_class(code, base_class)

        with open(code_file, "w", encoding="utf-8") as f:
            f.write(code)

        self.section_codes[section.id] = code
        return code

    def debug_and_fix_code(self, section_id: str, max_fix_attempts: int = 3) -> bool:
        """Enhanced debug and fix code method"""
        if section_id not in self.section_codes:
            return False

        for fix_attempt in range(max_fix_attempts):
            print(f"🔧 {self.learning_topic} Debugging {section_id} (attempt {fix_attempt + 1}/{max_fix_attempts})")

            try:
                scene_name = f"{section_id.title().replace('_', '')}Scene"
                code_file = f"{section_id}.py"
                cmd = ["manim", f"-q{self.video_quality}", str(code_file), scene_name]
                
                # 添加竖屏模式参数 (9:16 比例)
                # Manim 0.19.0 使用 -r 或 --resolution 参数
                if self.portrait_mode:
                    cmd.extend(["-r", "1080,1920"])

                result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.output_dir, timeout=180)

                if result.returncode == 0:
                    # 根据质量和模式确定输出目录名
                    # Manim 0.19.0 使用高度作为目录名：480p15, 720p30, 1080p60, 1920p15 等
                    quality_dirs = {
                        "l": "480p15",
                        "m": "720p30", 
                        "h": "1080p60",
                        "k": "2160p60"
                    }
                    # 竖屏模式下，分辨率是 1080x1920，manim 使用高度命名目录
                    if self.portrait_mode:
                        portrait_quality_dirs = {
                            "l": "1920p15",
                            "m": "1920p30",
                            "h": "1920p60",
                            "k": "1920p60"
                        }
                        quality_dir = portrait_quality_dirs.get(self.video_quality, "1920p15")
                    else:
                        quality_dir = quality_dirs.get(self.video_quality, "480p15")
                    
                    video_patterns = [
                        self.output_dir / "media" / "videos" / f"{code_file.replace('.py', '')}" / quality_dir / f"{scene_name}.mp4",
                        self.output_dir / "media" / "videos" / quality_dir / f"{scene_name}.mp4",
                    ]

                    for video_path in video_patterns:
                        if video_path.exists():
                            self.section_videos[section_id] = str(video_path)
                            print(f"✅ {self.learning_topic} {section_id} finished")
                            return True

                current_code = self.section_codes[section_id]
                fixed_code = self.scope_refine_fixer.fix_code_smart(section_id, current_code, result.stderr, self.output_dir)

                if fixed_code:
                    self.section_codes[section_id] = fixed_code
                    with open(self.output_dir / code_file, "w", encoding="utf-8") as f:
                        f.write(fixed_code)
                else:
                    break

            except subprocess.TimeoutExpired:
                print(f"❌ {self.learning_topic} {section_id} timed out")
                break
            except Exception as e:
                print(f"❌ {self.learning_topic} {section_id} failed with exception: {e}")
                break

        return False

    def get_mllm_feedback(self, section: Section, video_path: str, round_number: int = 1) -> VideoFeedback:
        print(f"🤖 {self.learning_topic} Using MLLM to analyze video ({round_number}/{self.feedback_rounds}): {section.id}")

        current_code = self.section_codes[section.id]
        positions = self.extractor.extract_grid_positions(current_code)
        position_table = self.extractor.generate_position_table(positions)
        analysis_prompt = get_prompt4_layout_feedback(section=section, position_table=position_table)

        def _parse_layout(feedback_content):
            has_layout_issues, suggested_improvements = False, []
            try:
                data = json.loads(feedback_content)
                lay = data.get("layout", {})
                has_layout_issues = bool(lay.get("has_issues", False))
                for it in lay.get("improvements", []) or []:
                    if isinstance(it, dict):
                        prob = str(it.get("problem", "")).strip()
                        sol = str(it.get("solution", "")).strip()
                        if prob or sol:
                            suggested_improvements.append(f"[LAYOUT] Problem: {prob}; Solution: {sol}")

            except json.JSONDecodeError:
                print(f"⚠️ {self.learning_topic} JSON parse failed, fallback to keyword analysis")

                for m in re.finditer(
                    r"Problem:\s*(.*?);\s*Solution:\s*(.*?)(?=\n|$)", feedback_content, flags=re.IGNORECASE | re.DOTALL
                ):
                    suggested_improvements.append(f"[LAYOUT] Problem: {m.group(1).strip()}; Solution: {m.group(2).strip()}")

                if not suggested_improvements:
                    for sol in re.findall(r"Solution\s*:\s*(.+)", feedback_content, flags=re.IGNORECASE):
                        suggested_improvements.append(f"[LAYOUT] Problem: ; Solution: {sol.strip()}")

            return has_layout_issues, suggested_improvements

        try:
            # 使用 Gemini 进行 MLLM 视频分析（gpt-5.1 不支持视频输入）
            response = request_gemini_video_img(prompt=analysis_prompt, video_path=video_path, image_path=self.GRID_IMG_PATH)
            feedback_content = extract_answer_from_response(response)
            has_layout_issues, suggested_improvements = _parse_layout(feedback_content)
            feedback = VideoFeedback(
                section_id=section.id,
                video_path=video_path,
                has_issues=has_layout_issues,
                suggested_improvements=suggested_improvements,
                raw_response=feedback_content,
            )
            self.video_feedbacks[f"{section.id}_round{round_number}"] = feedback
            return feedback

        except Exception as e:
            print(f"❌ {self.learning_topic} MLLM analysis failed: {str(e)}")
            return VideoFeedback(
                section_id=section.id,
                video_path=video_path,
                has_issues=False,
                suggested_improvements=[],
                raw_response=f"Error: {str(e)}",
            )

    def optimize_with_feedback(self, section: Section, feedback: VideoFeedback) -> bool:
        """Optimize the code based on feedback from the MLLM"""
        if not feedback.has_issues or not feedback.suggested_improvements:
            print(f"✅ {self.learning_topic} {section.id} no optimization needed")
            return True

        # === Step 1: back up original code ===
        original_code_content = self.section_codes[section.id]

        for attempt in range(self.max_feedback_gen_code_tries):
            print(
                f"🎯 {self.learning_topic} MLLM feedback optimization {section.id} code, attempt {attempt + 1}/{self.max_feedback_gen_code_tries}"
            )

            # === Step 2: back up original code and apply improvements ===
            if attempt > 0:
                self.section_codes[section.id] = original_code_content

            # === Step 3: re-generate code with feedback ===
            self.generate_section_code(
                section=section, attempt=attempt + 1, feedback_improvements=feedback.suggested_improvements
            )
            success = self.debug_and_fix_code(section.id, max_fix_attempts=self.max_mllm_fix_bugs_tries)
            if success:
                optimized_output_dir = self.output_dir / "optimized_videos"
                optimized_output_dir.mkdir(exist_ok=True)
                optimized_video_path = optimized_output_dir / f"{section.id}_optimized.mp4"

                if section.id in self.section_videos:
                    original_video_path = Path(self.section_videos[section.id])
                    if original_video_path.exists():
                        original_video_path.rename(optimized_video_path)
                        self.section_videos[section.id] = str(optimized_video_path)
                        print(f"✨ {self.learning_topic} {section.id} optimized video saved: {optimized_video_path}")
                    else:
                        print(f"⚠️ {self.learning_topic} {section.id} original video file not found: {original_video_path}")
                else:
                    print(f"⚠️ {self.learning_topic} {section.id} no optimized video path found")
                return True
            else:
                print(
                    f"❌ {self.learning_topic} {section.id} MLLM optimization failed, attempt {attempt + 1}/{self.max_feedback_gen_code_tries}"
                )

        return False

    def generate_codes(self) -> Dict[str, str]:
        if not self.sections:
            raise ValueError(f"{self.learning_topic} Please generate teaching sections first")

        def task(section):
            try:
                self.generate_section_code(section, attempt=1)
                return section.id, None
            except Exception as e:
                return section.id, e

        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {executor.submit(task, section): section for section in self.sections}
            for future in as_completed(futures):
                section_id, err = future.result()
                if err:
                    print(f"❌ {self.learning_topic} {section_id} code generation failed: {err}")

        return self.section_codes

    def render_section(self, section: Section) -> bool:
        section_id = section.id

        try:
            success = False
            for regenerate_attempt in range(self.max_regenerate_tries):
                # print(f"🎯 Processing {section_id} (regenerate attempt {regenerate_attempt + 1}/{self.max_regenerate_tries})")
                try:
                    if regenerate_attempt > 0:
                        self.generate_section_code(section, attempt=regenerate_attempt + 1)
                    success = self.debug_and_fix_code(section_id, max_fix_attempts=self.max_fix_bug_tries)
                    if success:
                        break
                    else:
                        pass
                except Exception as e:
                    print(f"⚠️ {section_id} attempt {regenerate_attempt + 1} raised exception: {str(e)}")
                    continue
            if not success:
                print(f"❌{self.learning_topic} {section_id} all failed, skipping section")
                return False

            # MLLM feedback
            if self.use_feedback:
                try:
                    for round in range(self.feedback_rounds):
                        current_video = self.section_videos.get(section_id)
                        if not current_video:
                            print(f"❌ {self.learning_topic} {section_id} no video available for MLLM feedback")
                            return success
                        try:
                            feedback = self.get_mllm_feedback(section, current_video, round_number=round + 1)

                            optimization_success = self.optimize_with_feedback(section, feedback)
                            if optimization_success:
                                pass
                            else:
                                print(
                                    f"⚠️ {self.learning_topic} {section_id} round {round+1} MLLM feedback optimization failed, using current version"
                                )
                        except Exception as e:
                            print(
                                f"⚠️ {self.learning_topic} {section_id} round {round+1} MLLM feedback processing exception: {str(e)}"
                            )
                            continue

                except Exception as e:
                    print(f"⚠️ {self.learning_topic} {section_id} MLLM feedback processing exception: {str(e)}")

            return success

        except Exception as e:
            print(f"❌ {self.learning_topic} {section_id} render process exception: {str(e)}")
            return False

    def render_section_worker(self, section_data) -> Tuple[str, bool, Optional[str]]:
        section_id = "unknown"
        try:
            section, agent_class, kwargs = section_data
            section_id = section.id
            agent = agent_class(**kwargs)
            success = agent.render_section(section)
            video_path = agent.section_videos.get(section.id) if success else None
            return section_id, success, video_path

        except Exception as e:
            print(f"❌ {self.learning_topic} {section_id} render process exception: {str(e)}")
            return section_id, False, None

    def render_all_sections(self, max_workers: int = 6) -> Dict[str, str]:
        print(f"🎥 Start parallel rendering of all section videos (up to {max_workers} processes)...")

        tasks = []
        for section in self.sections:
            try:
                task_data = (section, self.__class__, self.get_serializable_state())
                tasks.append(task_data)
            except Exception as e:
                print(f"⚠️ Error preparing task data for {section.id}: {str(e)}")
                continue

        if not tasks:
            print("❌ No valid tasks to execute")
            return {}

        results = {}
        successful_count = 0
        failed_count = 0

        try:
            with ProcessPoolExecutor(max_workers=max_workers) as executor:
                future_to_section = {}
                for task in tasks:
                    try:
                        future = executor.submit(self.render_section_worker, task)
                        future_to_section[future] = task[0].id
                    except Exception as e:
                        section_id = task[0].id if task and len(task) > 0 else "unknown"
                        print(f"⚠️ Error submitting task for {section_id}: {str(e)}")
                        failed_count += 1

                for future in as_completed(future_to_section):
                    section_id = future_to_section[future]
                    try:
                        sid, success, video_path = future.result(timeout=300)

                        if success and video_path:
                            results[sid] = video_path
                            successful_count += 1
                            print(f"✅ {sid} video rendered successfully: {video_path}")
                        else:
                            failed_count += 1
                            print(f"⚠️ {sid} video rendering failed")

                    except Exception as e:
                        failed_count += 1
                        print(f"❌ {section_id} video rendering process error: {str(e)}")

        except Exception as e:
            print(f"❌ Critical error in parallel rendering process: {str(e)}")

        # 更新结果并输出统计信息
        self.section_videos.update(results)

        total_sections = len(self.sections)
        print(f"\n📊 Rendering Statistics:")
        print(f"   Total Sections: {total_sections}")
        print(f"   Success Rate: {successful_count/total_sections*100:.1f}%" if total_sections > 0 else "   Success Rate: 0%")

        if successful_count == 0:
            print("❌ All section videos failed to render")
        elif failed_count > 0:
            print(
                f"⚠️ {failed_count} section videos failed to render, but {successful_count} section videos rendered successfully"
            )
        else:
            print("🎉 All section videos rendered successfully!")

        return results

    def merge_videos(self, output_filename: str = None) -> str:
        """Step 5: Merge all section videos"""
        if not self.section_videos:
            raise ValueError("No video files available to merge")

        if output_filename is None:
            safe_name = topic_to_safe_name(self.learning_topic)
            output_filename = f"{safe_name}.mp4"

        output_path = self.output_dir / output_filename

        print(f"🔗 Start merging section videos...")

        video_list_file = self.output_dir / "video_list.txt"
        with open(video_list_file, "w", encoding="utf-8") as f:
            for section_id in sorted(self.section_videos.keys()):
                video_path = self.section_videos[section_id].replace(f"{self.output_dir}/", "")
                f.write(f"file '{video_path}'\n")

        # ffmpeg
        try:
            result = subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(video_list_file), "-c", "copy", str(output_path)],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                return str(output_path)
            else:
                print(f"❌ Failed to merge section videos: {result.stderr}")
                return None
        except Exception as e:
            print(f"❌ Failed to merge section videos: {e}")
            return None

    def GENERATE_VIDEO(self) -> str:
        """Generate complete video with MLLM feedback optimization"""
        try:
            self.generate_outline()
            self.generate_storyboard()
            self.generate_codes()
            self.render_all_sections()
            final_video = self.merge_videos()
            if final_video:
                print(f"🎉 Video generated success: {final_video}")
                return final_video
            else:
                print(f"❌{self.learning_topic}  failed")
                return None
        except Exception as e:
            print(f"❌ Video generation failed: {e}")
            return None


def process_knowledge_point(idx, kp, folder_path: Path, cfg: RunConfig):
    print(f"\n🚀 Processing knowledge topic: {kp}")
    start_time = time.time()

    agent = TeachingVideoAgent(
        idx=idx,
        knowledge_point=kp,
        folder=folder_path,
        cfg=cfg,
    )
    video_path = agent.GENERATE_VIDEO()

    duration_minutes = (time.time() - start_time) / 60
    total_tokens = agent.token_usage["total_tokens"]

    print(f"✅ Knowledge topic '{kp}' processed. Cost Time: {duration_minutes:.2f} minutes, Tokens used: {total_tokens}")
    return kp, video_path, duration_minutes, total_tokens


def process_batch(batch_data, cfg: RunConfig):
    """Process a batch of knowledge points (serial within a batch)"""
    batch_idx, kp_batch, folder_path = batch_data
    results = []
    print(f"Batch {batch_idx + 1} starts processing {len(kp_batch)} knowledge points")

    for local_idx, (idx, kp) in enumerate(kp_batch):
        try:
            if local_idx > 0:
                delay = random.uniform(3, 6)
                print(f"⏳ Batch {batch_idx + 1} waits {delay:.1f}s before processing {kp}...")
                time.sleep(delay)
            results.append(process_knowledge_point(idx, kp, folder_path, cfg))
        except Exception as e:
            print(f"❌ Batch {batch_idx + 1} processing {kp} failed: {e}")
            results.append((kp, None, 0, 0))
    return batch_idx, results


def run_Code2Video(
    knowledge_points: List[str], folder_path: Path, parallel=True, batch_size=3, max_workers=8, cfg: RunConfig = RunConfig()
):
    all_results = []

    if parallel:
        batches = []
        for i in range(0, len(knowledge_points), batch_size):
            batch = [(i + j, kp) for j, kp in enumerate(knowledge_points[i : i + batch_size])]
            batches.append((i // batch_size, batch, folder_path))

        print(
            f"🔄 Parallel batch processing mode: {len(batches)} batches, each with {batch_size} knowledge points, {max_workers} concurrent batches"
        )
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(process_batch, batch, cfg): batch for batch in batches}
            for future in as_completed(futures):
                try:
                    batch_idx, batch_results = future.result()
                    all_results.extend(batch_results)
                    print(f"✅ Batch {batch_idx + 1} completed")
                except Exception as e:
                    print(f"❌ Batch {batch_idx + 1} processing failed: {e}")
    else:
        print("🔄 Serial processing mode")
        for idx, kp in enumerate(knowledge_points):
            try:
                all_results.append(process_knowledge_point(idx, kp, folder_path, cfg))
            except Exception as e:
                print(f"❌ Serial processing {kp} failed: {e}")
                all_results.append((kp, None, 0, 0))

    successful_runs = [r for r in all_results if r[1] is not None]
    total_runs = len(all_results)
    if not successful_runs:
        print("\nAll knowledge points failed, cannot calculate average.")
        return

    total_duration = sum(r[2] for r in successful_runs)
    total_tokens_consumed = sum(r[3] for r in successful_runs)
    num_successful = len(successful_runs)

    print("\n" + "=" * 50)
    print(f"   Total knowledge points: {total_runs}")
    print(f"   Successfully processed: {num_successful} ({num_successful/total_runs*100:.1f}%)")
    print(f"   Average duration [min]: {total_duration/num_successful:.2f} minutes/knowledge point")
    print(f"   Average token consumption: {total_tokens_consumed/num_successful:,.0f} tokens/knowledge point")
    print("=" * 50)


def get_api_and_output(API_name):
    mapping = {
        "gpt-41": (request_gpt41_token, "Chatgpt41"),
        "claude": (request_claude_token, "CLAUDE"),
        "gpt-5": (request_gpt5_token, "Chatgpt5"),
        "gpt-51": (request_gpt51_token, "Chatgpt51"),
        "gpt-4o": (request_gpt4o_token, "Chatgpt4o"),
        "gpt-o4mini": (request_o4mini_token, "Chatgpto4mini"),
        "Gemini": (request_gemini_token, "Gemini"),
    }
    try:
        return mapping[API_name]
    except KeyError:
        raise ValueError("Invalid API model name")


def build_and_parse_args():
    parser = argparse.ArgumentParser()
    # TODO: Core hyperparameters
    parser.add_argument(
        "--API",
        type=str,
        choices=["gpt-41", "claude", "gpt-5", "gpt-51", "gpt-4o", "gpt-o4mini", "Gemini"],
        default="gpt-41",
    )
    parser.add_argument(
        "--folder_prefix",
        type=str,
        default="TEST",
    )
    parser.add_argument("--knowledge_file", type=str, default="long_video_topics_list.json")
    parser.add_argument("--iconfinder_api_key", type=str, default="")

    # Basically invariant parameters
    parser.add_argument("--use_feedback", action="store_true", default=False)
    parser.add_argument("--no_feedback", action="store_false", dest="use_feedback")
    parser.add_argument("--use_assets", action="store_true", default=False)
    parser.add_argument("--no_assets", action="store_false", dest="use_assets")

    parser.add_argument("--max_code_token_length", type=int, help="max # token for generating code", default=10000)
    parser.add_argument("--max_fix_bug_tries", type=int, help="max # tries for SR to fix bug", default=10)
    parser.add_argument("--max_regenerate_tries", type=int, help="max # tries to regenerate", default=10)
    parser.add_argument("--max_feedback_gen_code_tries", type=int, help="max # tries for Critic", default=3)
    parser.add_argument("--max_mllm_fix_bugs_tries", type=int, help="max # tries for Critic to fix bug", default=3)
    parser.add_argument("--feedback_rounds", type=int, default=2)

    parser.add_argument("--parallel", action="store_true", default=False)
    parser.add_argument("--no_parallel", action="store_false", dest="parallel")
    parser.add_argument("--parallel_group_num", type=int, default=3)
    parser.add_argument("--max_concepts", type=int, help="Limit # concepts for a quick run, -1 for all", default=-1)
    parser.add_argument("--knowledge_point", type=str, help="if knowledge_file not given, can ignore", default=None)

    # 竖屏模式配置
    parser.add_argument("--portrait", action="store_true", default=True, help="竖屏模式 (9:16 比例，适合手机)")
    parser.add_argument("--landscape", action="store_false", dest="portrait", help="横屏模式 (16:9 比例)")
    parser.add_argument("--video_quality", type=str, default="l", choices=["l", "m", "h", "k"],
                        help="视频质量: l(低480p), m(中720p), h(高1080p), k(4K)")
    
    # 分阶段模型配置
    parser.add_argument("--api_stage1", type=str, default=None,
                        choices=["gpt-41", "claude", "gpt-5", "gpt-51", "gpt-4o", "gpt-o4mini", "Gemini"],
                        help="Stage 1 (Outline) 使用的模型，默认与 --API 相同")
    parser.add_argument("--api_stage2", type=str, default=None,
                        choices=["gpt-41", "claude", "gpt-5", "gpt-51", "gpt-4o", "gpt-o4mini", "Gemini"],
                        help="Stage 2 (Storyboard) 使用的模型，默认与 --API 相同")
    parser.add_argument("--api_stage3", type=str, default=None,
                        choices=["gpt-41", "claude", "gpt-5", "gpt-51", "gpt-4o", "gpt-o4mini", "Gemini"],
                        help="Stage 3 (Code Generation) 使用的模型，默认与 --API 相同")

    return parser.parse_args()


if __name__ == "__main__":
    args = build_and_parse_args()

    api, folder_name = get_api_and_output(args.API)
    # Add timestamp to make each run unique
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    folder = Path(__file__).resolve().parent / "CASES" / f"{args.folder_prefix}_{folder_name}_{timestamp}"

    _CFG_PATH = pathlib.Path(__file__).with_name("api_config.json")
    with _CFG_PATH.open("r", encoding="utf-8") as _f:
        _CFG = json.load(_f)
    iconfinder_cfg = _CFG.get("iconfinder", {})
    args.iconfinder_api_key = iconfinder_cfg.get("api_key")
    if args.iconfinder_api_key:
        print(f"Iconfinder API Key: {args.iconfinder_api_key}")
    else:
        print("WARNING: Iconfinder API key not found in config file. Using default (None).")

    if args.knowledge_point:
        print(f"🔄 Single knowledge point mode: {args.knowledge_point}")
        knowledge_points = [args.knowledge_point]
        args.parallel_group_num = 1
    elif args.knowledge_file:
        with open(Path(__file__).resolve().parent / "json_files" / args.knowledge_file, "r", encoding="utf-8") as f:
            knowledge_points = json.load(f)
            # max_concepts > 0 时才截取，-1 表示处理全部
            if args.max_concepts is not None and args.max_concepts > 0:
                knowledge_points = knowledge_points[: args.max_concepts]
    else:
        raise ValueError("Must provide --knowledge_point | --knowledge_file")

    # 解析各阶段的 API
    api_stage1 = get_api_and_output(args.api_stage1)[0] if args.api_stage1 else None
    api_stage2 = get_api_and_output(args.api_stage2)[0] if args.api_stage2 else None
    api_stage3 = get_api_and_output(args.api_stage3)[0] if args.api_stage3 else None

    cfg = RunConfig(
        api=api,
        api_stage1=api_stage1,
        api_stage2=api_stage2,
        api_stage3=api_stage3,
        iconfinder_api_key=args.iconfinder_api_key,
        use_feedback=args.use_feedback,
        use_assets=args.use_assets,
        max_code_token_length=args.max_code_token_length,
        max_fix_bug_tries=args.max_fix_bug_tries,
        max_regenerate_tries=args.max_regenerate_tries,
        max_feedback_gen_code_tries=args.max_feedback_gen_code_tries,
        max_mllm_fix_bugs_tries=args.max_mllm_fix_bugs_tries,
        feedback_rounds=args.feedback_rounds,
        portrait_mode=args.portrait,
        video_quality=args.video_quality,
    )

    print(f"📱 视频模式: {'竖屏 (9:16)' if args.portrait else '横屏 (16:9)'}")
    quality_names = {'l': '480p', 'm': '720p', 'h': '1080p', 'k': '4K'}
    print(f"🎬 视频质量: {quality_names[args.video_quality]}")
    
    # 打印各阶段使用的模型
    stage1_name = args.api_stage1 or args.API
    stage2_name = args.api_stage2 or args.API
    stage3_name = args.api_stage3 or args.API
    print(f"🤖 Stage 1 (Outline) 模型: {stage1_name}")
    print(f"🤖 Stage 2 (Storyboard) 模型: {stage2_name}")
    print(f"🤖 Stage 3 (Code) 模型: {stage3_name}")
    print(f"🤖 其他阶段 模型: {args.API}")

    run_Code2Video(
        knowledge_points,
        folder,
        parallel=args.parallel,
        batch_size=max(1, int(len(knowledge_points) / args.parallel_group_num)),
        max_workers=get_optimal_workers(),
        cfg=cfg,
    )
