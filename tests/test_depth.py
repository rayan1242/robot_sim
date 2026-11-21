import unittest
import numpy as np

from perception.depth import colorize_depth, prepare_depth_frame


class DepthVisualizationTests(unittest.TestCase):
    def test_negotiated_camera_size_is_letterboxed(self):
        frame = np.full((288, 544, 3), 255, np.uint8)
        result = prepare_depth_frame(frame, 480, 360)
        self.assertEqual(result.shape, (360, 480, 3))
        self.assertTrue((result[0] == 0).all())
        self.assertTrue((result[180] == 255).all())

    def test_matching_size_is_unchanged(self):
        frame = np.ones((240, 320, 3), np.uint8)
        self.assertIs(prepare_depth_frame(frame, 320, 240), frame)

    def test_constant_and_nonfinite_depth(self):
        for depth in [np.ones((12, 16), np.float32), np.full((12, 16), np.nan)]:
            color = colorize_depth(depth)
            self.assertEqual(color.shape, (12, 16, 3))
            self.assertEqual(color.dtype, np.uint8)

    def test_depth_gradient_has_distinct_colors(self):
        depth = np.arange(192, dtype=np.float32).reshape(12, 16)
        color = colorize_depth(depth)
        self.assertFalse(np.array_equal(color[0, 0], color[-1, -1]))
