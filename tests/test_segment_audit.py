import unittest
import numpy as np

from eval.audit_segment import pair_agreement


class SegmentAuditTests(unittest.TestCase):
    def test_known_plane_agrees_after_camera_translation(self):
        matrix=np.array([[50.,0,25],[0,50.,25],[0,0,1]])
        pose=np.eye(4);pose[0,3]=0.1
        depth=np.full((50,50),2.,np.float32)
        image=np.full((50,50,3),[10,20,30],np.uint8)
        points=np.array([[0.,0,2],[0.2,0,2]])
        colors=np.array([[30,20,10],[30,20,10]],np.uint8)
        result=pair_agreement(points,colors,pose,depth,image,matrix,np.zeros(5))
        self.assertEqual(result['valid_samples'],2)
        self.assertEqual(result['depth_abs_rel_median'],0)
        self.assertEqual(result['rgb_transfer_mean_abs_error_0_255'],0)

    def test_wrong_depth_and_missing_depth_are_not_silent_agreement(self):
        matrix=np.array([[50.,0,25],[0,50.,25],[0,0,1]])
        depth=np.full((50,50),2.,np.float32);image=np.zeros((50,50,3),np.uint8)
        result=pair_agreement(np.array([[0.,0,1.]]),np.zeros((1,3)),np.eye(4),depth,image,matrix,np.zeros(5))
        self.assertEqual(result['depth_abs_rel_median'],0.5)
        self.assertEqual(result['fraction_within_10_percent'],0)
        result=pair_agreement(np.array([[0.,0,1.]]),np.zeros((1,3)),np.eye(4),depth*np.nan,image,matrix,np.zeros(5))
        self.assertIsNone(result['depth_abs_rel_median'])
        self.assertEqual(result['valid_samples'],0)
