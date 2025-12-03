base_class = """
class TeachingScene(Scene):
    def setup_layout(self, title_text, lecture_lines):
        # BASE - Portrait Mode (9:16 aspect ratio, 1080x1920)
        self.camera.background_color = "#000000"
        
        # Title at top center (smaller for portrait)
        self.title = Text(title_text, font_size=32, color=WHITE)
        self.title.move_to(UP * 7)  # Top area in portrait mode
        self.add(self.title)

        # Lecture content at bottom (horizontal arrangement for portrait)
        lecture_texts = [Text(line, font_size=20, color=WHITE) for line in lecture_lines]
        self.lecture = VGroup(*lecture_texts).arrange(DOWN, aligned_edge=LEFT, buff=0.3).scale(0.7)
        self.lecture.move_to(DOWN * 6)  # Bottom area in portrait mode
        self.add(self.lecture)

        # Define fine-grained animation grid for Portrait Mode (4x8 grid)
        # Portrait canvas: X range [-4.5, 4.5], Y range [-8, 8]
        self.grid = {}
        rows = ["A", "B", "C", "D", "E", "F", "G", "H"]  # Top to bottom (8 rows for tall screen)
        cols = ["1", "2", "3", "4"]  # Left to right (4 columns for narrow screen)

        # Grid spacing for portrait: narrower horizontally, taller vertically
        for i, row in enumerate(rows):
            for j, col in enumerate(cols):
                x = -3 + j * 2  # X: -3 to 3 (narrower)
                y = 6 - i * 1.75  # Y: 6 to -6 (taller, excluding title/lecture areas)
                self.grid[f"{row}{col}"] = np.array([x, y, 0])

    def place_at_grid(self, mobject, grid_pos, scale_factor=1.0):
        mobject.scale(scale_factor)
        mobject.move_to(self.grid[grid_pos])
        return mobject

    def place_in_area(self, mobject, top_left, bottom_right, scale_factor=1.0):
        tl_pos = self.grid[top_left]
        br_pos = self.grid[bottom_right]
        
        # Calculate center of the area
        center_x = (tl_pos[0] + br_pos[0]) / 2
        center_y = (tl_pos[1] + br_pos[1]) / 2
        center = np.array([center_x, center_y, 0])
        
        mobject.scale(scale_factor)
        mobject.move_to(center)
        return mobject
"""
