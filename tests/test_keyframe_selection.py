import unittest
import numpy as np
from perception.keyframes import select_keyframes


class KeyframeSelectionTests(unittest.TestCase):
    def test_identical_overlapping_views_do_not_establish_baseline(self):
        landmarks={str(i):{'pos_w':[i/100,0,10]} for i in range(80)}
        def key(t,x):return {'ts':t,'rot_cw':[0,0,0,1],'trans_cw':[-x,0,0],'lm_ids':list(range(80))}
        keys=[key(0,0),key(1,0.01),key(2,0.5)]
        selected,decisions=select_keyframes(keys,landmarks,{0:100,1:100,2:100})
        self.assertEqual([k['ts'] for k in selected],[0,2])
        self.assertEqual(decisions[1]['status'],'insufficient_shared_baseline')

    def test_blurred_frame_is_not_a_seed_or_geometry_anchor(self):
        landmarks={str(i):{'pos_w':[i/100,0,10]} for i in range(80)}
        keys=[{'ts':t,'rot_cw':[0,0,0,1],'trans_cw':[-t,0,0],'lm_ids':list(range(80))} for t in [0,1]]
        selected,decisions=select_keyframes(keys,landmarks,{0:0,1:100})
        self.assertEqual([k['ts'] for k in selected],[1])
        self.assertEqual(decisions[0]['status'],'rejected_image_quality')
