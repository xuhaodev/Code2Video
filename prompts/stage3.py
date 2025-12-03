import os


def get_prompt3_code(regenerate_note, section, base_class):
    # 计算 section 总时长和每个动画的时长
    duration_seconds = getattr(section, 'duration_seconds', 60)
    
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
    
    timing_info = f"""
## 【重要】时间同步要求
- 本 Section 总时长：{duration_seconds} 秒
- 动画时长分配：{animation_durations}
- 动画时长总和：{total_animation_duration} 秒（必须与 Section 总时长一致）
- 每个动画步骤的 run_time 和 self.wait() 之和必须等于对应的时长
- 时间分配建议：
  - 主要动画效果：占分配时长的 60-70%
  - self.wait() 停顿（让学生理解）：占分配时长的 30-40%
- 示例：如果动画时长为 20 秒，可以用 run_time=12 的动画 + self.wait(8)

## 时间校验清单（生成代码后请确认）：
- [ ] Animation 1 总时长 = {animation_durations[0] if len(animation_durations) > 0 else 15}s
{chr(10).join([f'- [ ] Animation {i+2} 总时长 = {animation_durations[i+1]}s' for i in range(len(animation_durations)-1)]) if len(animation_durations) > 1 else ''}
- [ ] 所有动画总时长 = {total_animation_duration}s（应等于 Section 总时长 {duration_seconds}s）

## 时间控制代码示例：
```python
# 假设这个动画步骤分配了 20 秒
# === Animation for Lecture Line 1 (Duration: 20s) ===
self.play(self.lecture[0].animate.set_color("#FFFF00"), run_time=0.5)  # 0.5s
self.play(FadeIn(some_object), run_time=3)  # 3s
self.play(some_object.animate.shift(RIGHT * 2), run_time=4)  # 4s
self.wait(2)  # 让学生观察，2s
self.play(Transform(obj1, obj2), run_time=5)  # 5s
self.wait(5.5)  # 总结停顿，5.5s
# 总计：0.5 + 3 + 4 + 2 + 5 + 5.5 = 20 秒 ✓
```
"""

    return f"""
You are an expert Manim animator using Manim Community Edition v0.19.0. 
Please generate a high-quality Manim class based on the following teaching script.
{regenerate_note}

{timing_info}

1. Basic Requirements:
- Use the provided TeachingScene base class without modification.
- Each lecture line must have a matching color with its corresponding animation elements.
- Apply ONLY color changes to lecture lines - no scaling, translation, or Transform animations.

2. Visual Anchor System (MANDATORY):
- Use 6x6 grid system (A1-F6) for precise positioning.
- Pay attention to the positioning of elements to avoid occlusions (e.g., labels and formulas).
- All labels must be positioned within 1 grid unit of their corresponding objects
- Grid layout (right side only):
```
lecture |  A1  A2  A3  A4  A5  A6
        |  B1  B2  B3  B4  B5  B6
        |  C1  C2  C3  C4  C5  C6
        |  D1  D2  D3  D4  D5  D6
        |  E1  E2  E3  E4  E5  E6
        |  F1  F2  F3  F4  F5  F6
```

3. POSITIONING METHODS:
- Point example: self.place_at_grid(obj, 'B2', scale_factor=0.8)
- Area example: self.place_in_area(obj, 'A1', 'C3', scale_factor=0.7)
- NEVER use .to_edge(), .move_to(), or manual positioning!

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
- **TIME SYNC**: The total run_time + wait time for each animation block MUST equal the specified duration!
"""


def get_regenerate_note(attempt, MAX_REGENERATE_TRIES):
    return f"""    
**IMPORTANT NOTE:** This is attempt {attempt}/{MAX_REGENERATE_TRIES} to generate working code.
The previous attempts failed to run correctly. Please:
1. Use only basic, well-tested Manim functions
2. Avoid complex animations that might cause errors
3. Use simple, reliable Manim patterns
"""
