import tempfile
import unittest
from pathlib import Path

import numpy as np

from fuse_dataset import load_camera, resize_intrinsics


class FusionCameraTests(unittest.TestCase):
    def test_webcam_requires_explicit_calibration(self):
        with self.assertRaisesRegex(ValueError, "requires --calibration"):
            load_camera(None, Path("data/recordings/123"))

    def test_saved_camera_and_resize_pixel_convention(self):
        matrix = np.array([[950., 0, 320], [0, 940., 240], [0, 0, 1]])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/"camera.npz"
            np.savez(path, camera_matrix=matrix, distortion_coefficients=np.zeros(5), image_size=[640, 480])
            loaded, distortion, size = load_camera(path, Path("123"))
        resized = resize_intrinsics(loaded, size, (320, 240))
        self.assertEqual(resized[0, 0], 475)
        self.assertEqual(resized[0, 2], 159.75)
        self.assertEqual(resized[1, 2], 119.75)
        np.testing.assert_array_equal(loaded, matrix)
