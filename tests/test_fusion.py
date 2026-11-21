import unittest
import cv2
import numpy as np

from perception.fusion import fit_inverse_depth, project_landmarks, backproject, voxel_downsample, alignment_support, DepthAlignment, multiview_support


class FusionTests(unittest.TestCase):
    def test_multiview_rejects_floating_surface_and_keeps_plane(self):
        matrix = np.array([[100.,0,50],[0,100.,50],[0,0,1]])
        first = np.eye(4);second = np.eye(4);second[0,3] = 0.3
        depth = np.full((100,100),2.,np.float32)
        points = np.array([[0.,0,2],[0.,0,1.5],[0.,0,3.]])
        keep, stats = multiview_support(points,0,[(first,depth),(second,depth)],matrix,np.zeros(5))
        np.testing.assert_array_equal(keep,[True,False,False])
        self.assertEqual(stats['free_space_conflict_points'],1)

    def test_multiview_identical_views_and_unknown_depth_give_no_support(self):
        matrix = np.array([[100.,0,50],[0,100.,50],[0,0,1]])
        pose = np.eye(4);depth = np.full((100,100),2.,np.float32)
        keep,_ = multiview_support([[0,0,2]],0,[(pose,depth),(pose,depth)],matrix,np.zeros(5))
        self.assertFalse(keep[0])
        other = pose.copy();other[0,3]=0.3
        keep,_ = multiview_support([[0,0,2]],0,[(pose,depth),(other,depth*np.nan)],matrix,np.zeros(5))
        self.assertFalse(keep[0])

    def test_negative_depth_ordering_is_rejected_despite_small_residuals(self):
        x,y = np.meshgrid(np.arange(10),np.arange(10))
        uv = np.column_stack((x.ravel()*10,y.ravel()*10))
        values = np.linspace(0,1,100)
        depths = 1/(1.01-0.01*values)
        mask,stats = alignment_support(DepthAlignment(1e-8,1,100,100),np.ones((100,100)),uv,values,depths)
        self.assertIsNone(mask)
        self.assertIn('ordering',stats['rejection'])
    def test_supported_pixels_exclude_unobserved_image_regions(self):
        x, y = np.meshgrid(np.arange(20, 81, 5), np.arange(20, 81, 5))
        uv = np.column_stack((x.ravel(), y.ravel())).astype(float)
        values = uv[:, 0]/100
        depths = 1/(values+1)
        prediction = np.tile(np.arange(100)/100, (100, 1))
        mask, stats = alignment_support(DepthAlignment(1, 1, len(values), len(values)), prediction, uv, values, depths)
        self.assertIsNotNone(mask)
        self.assertTrue(mask[50, 50])
        self.assertFalse(mask[0, 50])
        self.assertFalse(mask[50, 99])

    def test_unreliable_training_support_is_rejected(self):
        uv = np.column_stack((np.arange(100), np.arange(100)))
        values = np.linspace(0, 1, 100)
        depths = 1/(values+1)
        depths[:40] *= 10
        mask, stats = alignment_support(DepthAlignment(1, 1, 60, 100), np.ones((100,100)), uv, values, depths)
        self.assertIsNone(mask)
        self.assertIn("70%", stats["rejection"])

    def test_alignment_rejects_outliers_and_predicts_heldout(self):
        rng = np.random.default_rng(8)
        network = rng.uniform(0, 4, 180)
        depth = 1/(0.7*network+0.2)
        corrupt = depth[:150].copy()
        corrupt[:35] *= 8
        result = fit_inverse_depth(network[:150], corrupt)
        heldout = result.depth(network[150:])
        self.assertLess(np.mean(np.abs(heldout-depth[150:])/depth[150:]), 1e-5)
        self.assertAlmostEqual(result.scale, 0.7, places=5)
        self.assertAlmostEqual(result.shift, 0.2, places=5)

    def test_degenerate_fit_is_rejected(self):
        with self.assertRaises(ValueError):
            fit_inverse_depth(np.ones(30), np.ones(30))

    def test_projection_backprojection_pose_and_distortion(self):
        matrix = np.array([[100., 0, 2], [0, 100., 2], [0, 0, 1]])
        distortion = np.array([0.1, -0.01, 0.001, -0.001, 0.0])
        pose = np.eye(4)
        pose[:3, :3], _ = cv2.Rodrigues(np.array([0.2, 0.1, 0.3]))
        pose[:3, 3] = [1, 2, 3]
        depth = np.full((5, 5), 2., np.float32)
        image = np.zeros((5, 5, 3), np.uint8)
        image[:] = [10, 20, 30]
        points, colors = backproject(depth, image, matrix, distortion, pose, stride=1)
        indices, uv, z = project_landmarks(points, pose, matrix, distortion, (5, 5))
        np.testing.assert_allclose(z, 2, atol=1e-8)
        self.assertGreater(len(indices), 8)
        np.testing.assert_allclose(uv, np.round(uv), atol=1e-6)
        np.testing.assert_array_equal(colors[0], [30, 20, 10])

    def test_voxel_centroids(self):
        points, colors = voxel_downsample(np.array([[0., 0, 0], [0.2, 0, 0], [2., 0, 0]]),
                                           np.array([[0, 0, 0], [100, 100, 100], [255, 255, 255]]), 1)
        self.assertEqual(len(points), 2)
        np.testing.assert_allclose(points[0], [0.1, 0, 0])
        np.testing.assert_array_equal(colors[0], [50, 50, 50])
