import json


def get_prompt2_storyboard(outline, reference_image_path):

    base_prompt = f""" 
    You are a professional education content designer, expert at converting teaching outlines into concise storyboard scripts for Manim animations.

    ## 定位：课后辅导视频
    这是面向中等学生的课后辅导内容，特点是：
    - 简洁精炼，直击要点
    - 每个 lecture line 都是干货
    - 动画用于强调关键概念，不要花哨
    - 整体节奏紧凑，不拖沓

    ## Task
    Convert the following teaching outline into a storyboard script:

    {outline}
    """

    # Add reference image guidance
    if reference_image_path:
        base_prompt += f"""

    ## Reference Image Available
    Use the reference image to guide animation design for key concepts.
    """

    base_prompt += """
    ## Storyboard Requirements
    
    ### Content Structure（精简原则）
    - 每个 section 最多 3-4 个 lecture lines
    - 每个 lecture line 对应 1 个动画
    - lecture line 必须简短精炼【不超过8个字】
    - 动画聚焦于展示核心概念，不要过度装饰

    ### 【重要】动画时间要求 - 与朗读时长同步
    - 每个 section 在 outline 中已包含 `estimated_duration_seconds` 和 `char_count`（字符数）
    - 时长计算方式：每5个字符约1秒朗读时间
    - 每个 section 必须输出 `duration_seconds`，值应等于 `estimated_duration_seconds`
    - 每个 animation 必须指定 `duration`（秒数）
    - 所有 animation 的 duration 之和 = section 的 duration_seconds
    - 每个动画时长应与对应 lecture_line 的内容量成正比
    - 课后辅导风格：节奏紧凑，动画与朗读同步

    ### 动画时长分配建议
    - 简短要点（5-10字）：8-12秒动画
    - 中等内容（10-20字）：12-20秒动画
    - 详细解释（20字以上）：20-30秒动画
    - 动画时长 = 动画效果 run_time + 停顿 wait 时间

    ### Visual Design
    - Background: #000000
    - Use bright, contrasting colors (provide hex codes)
    - 重点内容用醒目颜色（如 #FFE66D, #FF6B6B）

    ### Animation Effects（简洁为主）
    - 基础动画：出现、移动、颜色变化、淡入淡出
    - 强调效果：闪烁、高亮关键公式/要点
    - 避免复杂动画，追求清晰直观

    ### Constraints
    - 不使用3D效果
    - 不使用外部资源（SVG等）
    - 坐标轴只在必要时使用
    - 动画服务于理解，不要为了炫酷而复杂

    MUST output JSON format:
    {{
        "sections": [
            {{
                "id": "section_1",
                "title": "Sec 1: 核心概念",
                "duration_seconds": 52,
                "lecture_lines": ["要点一", "要点二", "要点三"],
                "animations": [
                    {{"step": 1, "duration": 18, "description": "..."}},
                    {{"step": 2, "duration": 17, "description": "..."}},
                    {{"step": 3, "duration": 17, "description": "..."}}
                ]
            }},
            ...
        ]
    }}
    
    Note: 
    - `duration_seconds` must match `estimated_duration_seconds` from outline（基于字符数计算）
    - Sum of animation durations = `duration_seconds`
    - 动画时长应与 talk script 朗读时长同步
    """

    return base_prompt


def get_prompt_download_assets(storyboard_data):
    return f"""
Analyze this educational video storyboard and identify at most 4 different ESSENTIAL visual elements that MUST be represented with downloadable icons/images (not manually drawn shapes).

Content:
{storyboard_data}

Selection Criteria:
1. Only choose elements that appear in **introduction** or **application** sections, and that are:
   - Real-world, recognizable physical objects
   - Visually distinctive enough that a generic shape would not be sufficient
   - Concrete, not abstract concepts
2. Prioritize: specific animals, characters, vehicles, tools, devices, landmarks, everyday objects
3. IGNORE and NEVER include:
   - Abstract concepts (e.g., justice, communication)
   - Symbols or icons for ideas (e.g., letters, formulas, diagrams, trees in data structure)
   - Geometric shapes, arrows, or math-related visuals
   - Any object composed entirely of basic shapes without unique visual identity

Output format:
- Output ONLY the object keywords, each keyword must be one word, one per line, all lowercase, no numbering, no extra text.
"""


def get_prompt_place_assets(asset_mapping, animations_structure):
    return f"""
You need to enhance only the animations by incorporating downloaded assets where appropriate.

Asset list:
{asset_mapping}

Current Animations Data:
{animations_structure}

Instructions:
- For each animation, determine if any downloaded assets should be incorporated.
- Only choose the most relevant asset for the animation step that needs.
- Insert the **abstract path** of asset in the form: [Asset: XXX].
- CAN ONLY use the assets in **THE FIRST and THE LAST** sections.
- Keep the same structure: return an array with section_index, section_id, and enhanced animations.
- Only modify the animation descriptions to include asset references.
- Do not change section_index or section_id.

Return only the enhanced animations data as valid JSON array:
"""
