import unittest
import numpy as np

from eval.compare_slam import compare


class ComparisonTests(unittest.TestCase):
    def test_common_coverage_and_independent_scale(self):
        rng = np.random.default_rng(32)
        positions = rng.normal(size=(12, 3))
        truth = np.column_stack((np.arange(12.), positions, np.tile([0, 0, 0, 1], (12, 1))))
        mini = truth.copy()
        mini[:, 1:4] = 3 * positions + [1, 2, 3]
        slam = truth[3:].copy()
        slam[:, 1:4] = positions[3:] / 2 - [3, 2, 1]
        report, target, trajectories = compare(mini, slam, truth)
        self.assertEqual(report["common_pose_count"], 9)
        self.assertEqual(report["systems"]["mini_vo"]["output_poses"], 12)
        for result in report["systems"].values():
            self.assertLess(result["ate_rmse_m"], 1e-10)

