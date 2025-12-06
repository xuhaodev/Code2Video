import os


def get_prompt3_code(regenerate_note, section, base_class):
    # 计算 section 总时长和每个动画的时长
    duration_seconds = getattr(section, 'duration_seconds', 60)
    talk_script = getattr(section, 'talk_script', '')
    
    # 计算 talk_script 的字符数（用于验证时长）
    talk_script_chars = len(talk_script.replace(' ', '').replace('\n', '').replace('\t', '')) if talk_script else 0
    
    # 解析动画时长信息
    animation_durations = []
    animations_text = []
    for anim in section.animations:
        if isinstance(anim, dict):
            animation_durations.append(anim.get('duration', 15))
            animations_text.append(anim.get('description', str(anim)))
        else:
            # 兼容旧格式
            animation_durations.append(duration_seconds // len(section.animations))
            animations_text.append(str(anim))
    
    # 计算动画时长总和，用于校验
    total_animation_duration = sum(animation_durations)
    
    # Talk Script 参考信息
    talk_script_info = ""
    if talk_script:
        talk_script_info = f"""
## 【参考】本节的 Talk Script（朗读稿）
以下是本节对应的完整朗读内容，共 {talk_script_chars} 个字符，预计朗读时长约 {talk_script_chars // 5} 秒。
动画应该配合这段朗读内容的节奏和重点：

\"\"\"{talk_script}\"\"\"

请根据 talk script 的内容节奏来设计动画：
- 当朗读到关键概念时，对应的视觉元素应该出现或高亮
- 当朗读到公式时，公式应该在屏幕上展示
- 当朗读到例题时，例题演示应该同步进行
- 停顿时间应该与朗读节奏匹配
"""
    
    timing_info = f"""
## 【核心要求】动画与朗读时长精确同步
- 本 Section 总时长：{duration_seconds} 秒（基于 talk script 字符数计算，每5个字符约1秒）
- Talk Script 字符数：{talk_script_chars} 字符
- 动画时长分配：{animation_durations}
- 动画时长总和：{total_animation_duration} 秒（必须与 Section 总时长一致）

{talk_script_info}

### 时间同步原则（非常重要！）
- 每个动画步骤的 run_time 和 self.wait() 之和必须**精确等于**对应的分配时长
- 动画时长与朗读时长同步，学生边听边看，动画与讲解内容匹配
- **严禁**动画过短（观众等待空白画面）或过长（讲解已结束动画还在播）

### 时间分配技巧
- 文字/公式出现动画：run_time=1-2秒
- 强调/高亮动画：run_time=0.5-1秒  
- 位移/变换动画：run_time=2-4秒
- 观察停顿 self.wait()：占分配时长的 30-50%
- 如果分配时长较长（>15秒），拆分成多个小动画 + 合理停顿

### 时间校验清单（生成代码后请核对）：
- [ ] Animation 1 总时长 = {animation_durations[0] if len(animation_durations) > 0 else 15}s
{chr(10).join([f'- [ ] Animation {i+2} 总时长 = {animation_durations[i+1]}s' for i in range(len(animation_durations)-1)]) if len(animation_durations) > 1 else ''}
- [ ] 所有动画总时长 = {total_animation_duration}s（应等于 Section 总时长 {duration_seconds}s）

### 时间控制代码示例：
```python
# 假设这个动画步骤分配了 18 秒
# === Animation for Lecture Line 1 (Duration: 18s) ===
self.play(self.lecture[0].animate.set_color("#FFFF00"), run_time=0.5)  # 0.5s - 高亮当前讲解
self.play(FadeIn(formula), run_time=1.5)  # 1.5s - 公式出现
self.play(formula.animate.set_color("#FF6B6B"), run_time=1)  # 1s - 强调
self.wait(3)  # 3s - 让学生阅读公式
self.play(Create(arrow), run_time=2)  # 2s - 指示箭头
self.play(FadeIn(explanation), run_time=1.5)  # 1.5s - 解释文字
self.wait(4)  # 4s - 让学生理解
self.play(FadeOut(arrow), run_time=0.5)  # 0.5s - 清理
self.wait(3.5)  # 3.5s - 总结停顿
# 总计：0.5 + 1.5 + 1 + 3 + 2 + 1.5 + 4 + 0.5 + 3.5 = 18 秒 ✓
```
"""

    return f"""
You are an expert Manim animator using Manim Community Edition v0.19.0. 
Please generate a high-quality Manim class based on the following teaching script.
{regenerate_note}

{timing_info}

**【重要】竖屏模式 (Portrait Mode - 9:16 比例)**
- 画布尺寸：1080x1920 像素，frame_width=9, frame_height=16
- 布局采用上下结构：顶部标题区 → 中间动画区 → 底部讲解文字区
- 所有元素必须考虑竖屏比例，避免左右过宽

1. Basic Requirements:
- Use the provided TeachingScene base class without modification.
- Each lecture line must have a matching color with its corresponding animation elements.
- Apply ONLY color changes to lecture lines - no scaling, translation, or Transform animations.

2. Visual Anchor System for Portrait Mode (MANDATORY):
- Use 4x8 grid system (A1-D8) for precise positioning on portrait canvas.
- Pay attention to the positioning of elements to avoid occlusions (e.g., labels and formulas).
- All labels must be positioned within 1 grid unit of their corresponding objects
- Grid layout for portrait mode (vertical orientation):
```
        |  A1  A2  A3  A4  |  ← Top (Title area)
        |  B1  B2  B3  B4  |
        |  C1  C2  C3  C4  |  ← Upper-middle (Main animation area)
        |  D1  D2  D3  D4  |
        |  E1  E2  E3  E4  |  ← Lower-middle (Secondary content)
        |  F1  F2  F3  F4  |
        |  G1  G2  G3  G4  |  ← Bottom (Lecture lines area)
        |  H1  H2  H3  H4  |
```
- Coordinate ranges: X: [-4.5, 4.5], Y: [-8, 8]

3. POSITIONING METHODS:
- Point example: self.place_at_grid(obj, 'C2', scale_factor=0.8)
- Area example: self.place_in_area(obj, 'B1', 'E4', scale_factor=0.7)
- NEVER use .to_edge(), .move_to(), or manual positioning!
- For portrait mode: prefer vertical layouts, stack elements top-to-bottom

4. TEACHING CONTENT:
- Title: {section.title}
- Section Duration: {duration_seconds} seconds
- Lecture Lines: {section.lecture_lines}
- Animation Description with Durations: {'; '.join([f"[{animation_durations[i]}s] {animations_text[i]}" for i in range(len(animations_text))])}

5. STRUCTURE FOR CODE:
Use the following comment format to indicate which block corresponds to which line AND its duration:
```python
# === Animation for Lecture Line 1 (Duration: {animation_durations[0] if animation_durations else 15}s) ===

6. EXAMPLE STRUCTURE:
```python
from manim import *

{base_class}

class {section.id.title().replace('_', '')}Scene(TeachingScene):
    def construct(self):
        self.setup_layout("{section.title}", {section.lecture_lines})
        
        # === Animation for Lecture Line 1 (Duration: XXs) ===
        # 动画代码，run_time 和 wait 之和 = XX 秒
        ...

        # === Animation for Lecture Line 2 (Duration: XXs) ===
        # 动画代码，run_time 和 wait 之和 = XX 秒
        ...
```

7. MANDATORY CONSTRAINTS:
- Colors: Use light, distinguishable hexadecimal colors.
- Scaling: Maintain appropriate font sizes and object scales for readability.
- Consistency: Do not apply any animation to the lecture lines except for color changes; The lecture lines and title's size and position must remain unchanged.
- Assets: If provided, MUST use the elements in the Animation Description formatted as [Asset: XXX/XXX.png] (abstract path).
- Simplicity: Avoid 3D functions, complex panels, or external dependencies except for filenames in Animation Description.
- **【最重要】TIME SYNC**: 每个动画块的 run_time + wait 总和必须精确等于分配时长！动画与朗读同步是核心目标！
"""


def get_regenerate_note(attempt, MAX_REGENERATE_TRIES):
    return f"""    
**IMPORTANT NOTE:** This is attempt {attempt}/{MAX_REGENERATE_TRIES} to generate working code.
The previous attempts failed to run correctly. Please:
1. Use only basic, well-tested Manim functions
2. Avoid complex animations that might cause errors
3. Use simple, reliable Manim patterns
"""
