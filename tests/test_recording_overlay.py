import unittest

from chirp.recording_overlay import compute_cursor_adjacent_geometry, compute_top_center_geometry


class TestRecordingOverlay(unittest.TestCase):
    def test_compute_top_center_geometry(self):
        geometry = compute_top_center_geometry(1920, width=280, height=42, top_margin=16)
        self.assertEqual(geometry.width, 280)
        self.assertEqual(geometry.height, 42)
        self.assertEqual(geometry.x, 820)
        self.assertEqual(geometry.y, 16)

    def test_compute_top_center_geometry_clamps_x(self):
        geometry = compute_top_center_geometry(200, width=280, height=42, top_margin=16)
        self.assertEqual(geometry.x, 0)
        self.assertEqual(geometry.y, 16)

    def test_compute_cursor_adjacent_geometry_offsets_from_cursor(self):
        geometry = compute_cursor_adjacent_geometry(
            100,
            200,
            screen_x=0,
            screen_y=0,
            screen_width=1920,
            screen_height=1080,
            width=168,
            height=40,
            offset=18,
        )
        self.assertEqual(geometry.x, 118)
        self.assertEqual(geometry.y, 218)

    def test_compute_cursor_adjacent_geometry_flips_at_edges(self):
        geometry = compute_cursor_adjacent_geometry(
            1910,
            1070,
            screen_x=0,
            screen_y=0,
            screen_width=1920,
            screen_height=1080,
            width=168,
            height=40,
            offset=18,
        )
        self.assertEqual(geometry.x, 1724)
        self.assertEqual(geometry.y, 1012)

    def test_compute_cursor_adjacent_geometry_supports_negative_monitor_origin(self):
        geometry = compute_cursor_adjacent_geometry(
            -1260,
            20,
            screen_x=-1280,
            screen_y=0,
            screen_width=3200,
            screen_height=1080,
            width=168,
            height=40,
            offset=18,
        )
        self.assertEqual(geometry.x, -1242)
        self.assertEqual(geometry.y, 38)


if __name__ == "__main__":
    unittest.main()
