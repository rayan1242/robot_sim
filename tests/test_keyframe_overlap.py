import unittest
import numpy as np
from eval.keyframe_overlap import pair_geometry


class KeyframeOverlapTests(unittest.TestCase):
    def test_overlap_and_angle_are_separate_measurements(self):
        first={'ts':0,'rot_cw':[0,0,0,1],'trans_cw':[1,0,0],'lm_ids':[1,-1]}
        second={'ts':1,'rot_cw':[0,0,0,1],'trans_cw':[-1,0,0],'lm_ids':[1]}
        result=pair_geometry(first,second,{'1':{'pos_w':[0,0,10]}})
        self.assertEqual(result['shared_fraction_of_smaller_view'],1)
        self.assertAlmostEqual(result['median_ray_angle_deg'],np.degrees(2*np.arctan(.1)))
        second['trans_cw']=[1,0,0]
        self.assertAlmostEqual(pair_geometry(first,second,{'1':{'pos_w':[0,0,10]}})['median_ray_angle_deg'],0,places=5)
