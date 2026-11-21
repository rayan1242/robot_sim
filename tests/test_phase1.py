import argparse
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import cv2
import numpy as np

from perception.capture import CameraCapture
from perception.calibrate import solve


class FakeCamera:
    def __init__(self, *args):
        self.released = False
        self.fail = False

    def isOpened(self):
        return True

    def getBackendName(self):
        return "FAKE"

    def set(self, *args):
        return False

    def get(self, *args):
        return 0

    def read(self):
        time.sleep(0.005)
        return (False, None) if self.fail else (True, np.zeros((48, 64, 3), np.uint8))

    def release(self):
        self.released = True


class PhaseOneTests(unittest.TestCase):
    def test_explicit_auto_exposure_and_manual_conflict(self):
        for backend,automatic,expected in [('DSHOW',True,1),('DSHOW',False,0),('V4L2',True,0.75)]:
            device=FakeCamera()
            with patch.object(device,'getBackendName',return_value=backend),patch.object(device,'set',return_value=True) as setter,patch('perception.capture.cv2.VideoCapture',return_value=device):
                with CameraCapture(auto_exposure=automatic) as capture:
                    setter.assert_any_call(cv2.CAP_PROP_AUTO_EXPOSURE,expected)
                    self.assertEqual(capture.settings['auto_exposure']['requested'],expected)
        with self.assertRaisesRegex(ValueError,'automatic exposure'):
            CameraCapture(auto_exposure=True,exposure=-5)

    def test_latest_frame_and_shutdown(self):
        device = FakeCamera()
        with patch("perception.capture.cv2.VideoCapture", return_value=device):
            with CameraCapture() as capture:
                first = capture.get_latest()
                time.sleep(0.08)
                latest = capture.get_latest(first.sequence)
                self.assertGreater(latest.sequence, first.sequence + 1)
                self.assertGreater(latest.captured_at, first.captured_at)
                self.assertLess(time.perf_counter() - latest.captured_at, 0.1)
                self.assertFalse(latest.image.flags.writeable)
            self.assertTrue(device.released)
            self.assertFalse(capture._thread.is_alive())

    def test_failure_propagates_and_releases(self):
        device = FakeCamera()
        device.fail = True
        with patch("perception.capture.cv2.VideoCapture", return_value=device):
            with self.assertRaisesRegex(RuntimeError, "10 consecutive"):
                with CameraCapture():
                    pass
        self.assertTrue(device.released)

    def test_synthetic_calibration(self):
        matrix = np.array([[600., 0, 320], [0, 610., 240], [0, 0, 1]])
        board = np.zeros((54, 3), np.float32)
        board[:, :2] = np.mgrid[0:9, 0:6].T.reshape(-1, 2) * 0.025
        observations = []
        for i in range(15):
            points, _ = cv2.projectPoints(board, np.array([0.03*i, -0.02*i, 0.01*i]),
                                          np.array([-0.1 + i*0.003, -0.08, 0.6 + i*0.02]),
                                          matrix, np.zeros(5))
            observations.append(points.astype(np.float32))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for i in range(15):
                cv2.imwrite(str(root / f"frame_{i:04d}.png"), np.zeros((480, 640, 3), np.uint8))
            args = argparse.Namespace(columns=9, rows=6, square_size=0.025,
                                      images=root, output=root / "calibration.npz")
            with patch("perception.calibrate.detect", side_effect=observations):
                solve(args)
            with np.load(args.output) as result:
                self.assertLess(float(result["rms"]), 0.01)
                np.testing.assert_allclose(result["camera_matrix"], matrix, atol=0.1)


if __name__ == "__main__":
    unittest.main()
