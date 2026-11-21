import unittest
import cv2
import numpy as np

from perception.vo import recover_motion, compose_camera_pose, VisualOdometry
from eval.trajectory import associate, align_similarity


class OdometryTests(unittest.TestCase):
    def test_synthetic_motion_direction_and_pose_convention(self):
        rng = np.random.default_rng(12)
        points = rng.uniform([-1, -1, 4], [1, 1, 9], (200, 3))
        matrix = np.array([[500., 0, 320], [0, 500., 240], [0, 0, 1]])
        vector = np.array([0.01, 0.03, -0.01])
        rotation, _ = cv2.Rodrigues(vector)
        translation = np.array([0.3, 0.02, 0.01])
        p, _ = cv2.projectPoints(points, np.zeros(3), np.zeros(3), matrix, None)
        q, _ = cv2.projectPoints(points, vector, translation, matrix, None)
        cv2.setRNGSeed(0)
        result = recover_motion(p, q, matrix, np.zeros(5))
        self.assertIsNotNone(result)
        recovered_r, recovered_t, count = result
        np.testing.assert_allclose(recovered_r, rotation, atol=0.01)
        self.assertGreater(np.dot(recovered_t, translation/np.linalg.norm(translation)), 0.99)
        pose = compose_camera_pose(np.eye(4), recovered_r, recovered_t)
        np.testing.assert_allclose(pose[:3, 3], -recovered_r.T @ recovered_t)

    def test_blank_frames_hold_pose(self):
        vo = VisualOdometry()
        vo.update(np.zeros((480, 640, 3), np.uint8))
        pose, status = vo.update(np.zeros((480, 640, 3), np.uint8))
        self.assertEqual(status["status"], "lost")
        np.testing.assert_array_equal(pose, np.eye(4))

    def test_similarity_alignment(self):
        rng = np.random.default_rng(7)
        source = rng.normal(size=(50, 3))
        rotation, _ = cv2.Rodrigues(np.array([0.1, 0.4, -0.3]))
        target = 2.5 * source @ rotation.T + [3, 1, -5]
        aligned, scale = align_similarity(source, target)
        np.testing.assert_allclose(aligned, target, atol=1e-10)
        self.assertAlmostEqual(scale, 2.5)

    def test_association_is_one_to_one(self):
        estimate = np.array([[1., 0], [1.005, 0], [2., 0], [3., 0]])
        truth = np.array([[1.001, 0], [2.001, 0], [3.001, 0]])
        a, b = associate(estimate, truth)
        self.assertEqual(len(a), 3)
        self.assertEqual(len(np.unique(b[:, 0])), 3)
