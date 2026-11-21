import copy
import unittest
import numpy as np

from perception.keyframe_window import ActiveKeyframeWindow


class KeyframeWindowTests(unittest.TestCase):
    def test_diverse_window_keeps_supported_older_anchor_within_bound(self):
        points={i:[(i%10)/10,(i//10)/10,2.] for i in range(100)}
        accepted=[]
        for i,x in enumerate([0,.1,.101,.102,.103]):
            pose=np.eye(4);pose[0,3]=x
            accepted.append({'key':{'id':i,'timestamp':i,'pose':pose.ravel().tolist(),'landmark_ids':list(points)}})
        old=ActiveKeyframeWindow(window_policy='newest').select_window(accepted,points)
        new=ActiveKeyframeWindow(window_policy='diverse').select_window(accepted,points)
        self.assertEqual([v['key']['id'] for v in old],[1,2,3,4])
        self.assertEqual(len(new),4)
        self.assertIn(0,[v['key']['id'] for v in new])
        self.assertIn(4,[v['key']['id'] for v in new])

    def setUp(self):
        self.matrix=np.array([[100.,0,50],[0,100.,50],[0,0,1]])
        u,v=np.meshgrid(np.arange(15,86,5),np.arange(15,86,5));z=1/(.5+u.ravel()/100)
        points=np.column_stack(((u.ravel()-50)/100*z,(v.ravel()-50)/100*z,z))
        self.reply={'map_epoch':0,'pose':np.eye(4).reshape(-1).tolist(),
            'landmarks':[[i,*p] for i,p in enumerate(points)],'keyframes':[]}
        for i,x in enumerate([0,.1,.2,.3]):
            pose=np.eye(4);pose[0,3]=x
            self.reply['keyframes'].append({'id':i,'timestamp':i,'pose':pose.reshape(-1).tolist(),'landmark_ids':list(range(len(points)))})
        self.image=np.full((100,100,3),[10,20,30],np.uint8)
        self.prediction=np.tile(.5+np.arange(100)/100,(100,1)).astype(np.float32)

    def update(self,window,reply=None):
        return window.update(reply or self.reply,lambda t:self.image,lambda img:self.prediction,self.matrix,np.zeros(5),(100,100))

    def test_window_needs_second_view_and_rebuilds_corrected_poses(self):
        window=ActiveKeyframeWindow(window_size=2,cache_size=3,min_sharpness=0)
        first=self.update(window)
        self.assertEqual(first[3]['dense_points'],0)
        points,_,_,status=self.update(window)
        self.assertGreater(status['dense_points'],0)
        # Freeze candidate set so this tests pose correction, not adding another view.
        original=copy.deepcopy(self.reply);original['keyframes']=original['keyframes'][:2]
        before=self.update(window,original)[0]
        corrected=copy.deepcopy(original)
        for row in corrected['landmarks']:row[1]+=1
        for key in corrected['keyframes']:key['pose'][3]+=1
        after=self.update(window,corrected)[0]
        self.assertEqual(before.shape,after.shape)
        np.testing.assert_allclose(after,before+[1,0,0],atol=1e-6)

    def test_older_anchor_allows_useful_candidate_without_relaxing_geometry(self):
        reply=copy.deepcopy(self.reply);reply['keyframes']=reply['keyframes'][:3]
        reply['keyframes'][2]['pose'][3]=.101
        for policy,expected in [('newest',[0,1]),('all_cached',[0,1,2])]:
            window=ActiveKeyframeWindow(min_sharpness=0,selection_policy=policy)
            for _ in range(3):status=self.update(window,reply)[3]
            self.assertEqual([i[0] for i in window.items],expected)
            if policy=='all_cached':
                self.assertEqual(status['candidate_decisions'][-1]['geometry_anchor_id'],0)
            landmarks={r[0]:r[1:] for r in reply['landmarks']}
            self.assertFalse(window.geometry_ok(reply['keyframes'][1],reply['keyframes'][2],landmarks))
            self.assertTrue(window.geometry_ok(reply['keyframes'][0],reply['keyframes'][2],landmarks))

    def test_bounded_cache_culling_and_map_reset(self):
        window=ActiveKeyframeWindow(window_size=2,cache_size=3,min_sharpness=0)
        for _ in range(5):result=self.update(window)
        self.assertLessEqual(result[3]['prediction_cache_size'],3)
        self.assertLessEqual(len(result[3]['window_keyframes']),2)
        empty={'map_epoch':1,'pose':None,'landmarks':[],'keyframes':[]}
        points,_,pose,status=self.update(window,empty)
        self.assertEqual(len(points),0);self.assertIsNone(pose)
        self.assertEqual(status['prediction_cache_size'],0)

    def test_culled_keyframes_are_removed_and_old_evictions_are_not_reinferred(self):
        window=ActiveKeyframeWindow(window_size=2,cache_size=3,min_sharpness=0)
        for _ in range(5):self.update(window)
        self.assertEqual([key[0] for key in window.items],[1,2,3])
        reply=copy.deepcopy(self.reply);reply['keyframes']=[k for k in reply['keyframes'] if k['id']!=2]
        self.update(window,reply)
        self.assertNotIn(2,[key[0] for key in window.items])

    def test_contradictory_depth_does_not_enter_dense_window(self):
        window=ActiveKeyframeWindow(window_size=2,cache_size=3,min_sharpness=0)
        self.prediction=self.prediction[:,::-1].copy()
        for _ in range(3):result=self.update(window)
        self.assertEqual(result[3]['dense_points'],0)
        self.assertEqual(result[3]['state'],'sparse_only')

    def test_removal_diagnostics_distinguish_omission_and_active_map_absence(self):
        for present,reason in [(True,'omitted_from_metadata_window'),(False,'absent_from_active_map_snapshot')]:
            window=ActiveKeyframeWindow(min_sharpness=0)
            self.update(window)
            reply=copy.deepcopy(self.reply)
            reply['active_keyframes']=[{'id':k['id'],'timestamp':k['timestamp']} for k in reply['keyframes'] if present or k['id']!=0]
            reply['keyframes']=reply['keyframes'][1:]
            status=self.update(window,reply)[3]
            self.assertEqual(status['keyframe_removals'][0]['reason'],reason)
            self.assertEqual(status['keyframe_removals'][0]['id'],0)

    def test_scale_correction_refits_cached_depth_without_old_scale_ghosts(self):
        window=ActiveKeyframeWindow(window_size=2,cache_size=3,min_sharpness=0)
        reply=copy.deepcopy(self.reply);reply['keyframes']=reply['keyframes'][:2]
        self.update(window,reply);before=self.update(window,reply)[0]
        np.testing.assert_allclose(before[:,0]+before[:,2],1,atol=1e-5)
        scaled=copy.deepcopy(reply)
        for row in scaled['landmarks']:row[1:]=[2*x for x in row[1:]]
        for key in scaled['keyframes']:
            for axis in [3,7,11]:key['pose'][axis]*=2
        after=self.update(window,scaled)[0]
        np.testing.assert_allclose(after[:,0]+after[:,2],2,atol=1e-5)

    def test_tracking_loss_keeps_existing_window_but_does_not_infer_new_views(self):
        window=ActiveKeyframeWindow(window_size=2,cache_size=3,min_sharpness=0)
        reply=copy.deepcopy(self.reply);reply['keyframes']=reply['keyframes'][:2]
        self.update(window,reply);before=self.update(window,reply)[0]
        lost=copy.deepcopy(self.reply);lost['pose']=None
        def forbidden(image):raise AssertionError('New depth inference during lost tracking')
        after,_,pose,status=window.update(lost,lambda t:self.image,forbidden,self.matrix,np.zeros(5),(100,100))
        self.assertIsNone(pose)
        self.assertEqual(status['prediction_cache_size'],2)
        np.testing.assert_allclose(after,before)
