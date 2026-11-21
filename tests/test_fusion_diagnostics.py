import unittest
import numpy as np

from eval.diagnose_fusion import audit_keyframe, triangulation_angles


class DiagnosticTests(unittest.TestCase):
    def test_projection_uses_camera_to_world_inverse(self):
        matrix = np.array([[100., 0, 320], [0, 100., 240], [0, 0, 1]])
        keyframe = {"rot_cw": [0, 0, 0, 1], "trans_cw": [-1, 0, 0],
                    "lm_ids": [3], "undist_keypts": [{"pt": [320, 240]}]}
        pose, points, errors = audit_keyframe(keyframe, {"3": {"pos_w": [1, 0, 5]}}, matrix)
        np.testing.assert_allclose(pose[:3, 3], [1, 0, 0])
        np.testing.assert_allclose(errors, 0)

    def test_ray_angle_for_known_baseline(self):
        data = {"landmarks": {"3": {"pos_w": [0, 0, 10]}}, "keyframes": {
            "0": {"rot_cw": [0,0,0,1], "trans_cw": [1,0,0], "lm_ids": [3]},
            "1": {"rot_cw": [0,0,0,1], "trans_cw": [-1,0,0], "lm_ids": [3]}}}
        self.assertAlmostEqual(triangulation_angles(data)[0], np.degrees(2*np.arctan(0.1)))
