import unittest
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np

from perception.live_slam import live_cloud,SlamProcess
from perception.capture import FramePacket
from types import SimpleNamespace


class LiveSlamTests(unittest.TestCase):
    def test_dataset_calibration_cannot_use_webcam_profile(self):
        from perception.vo import FR1_MATRIX,FR1_DISTORTION
        with TemporaryDirectory() as directory:
            calibration=Path(directory)/'tum.npz'
            np.savez(calibration,camera_matrix=FR1_MATRIX,distortion_coefficients=FR1_DISTORTION,image_size=[640,480])
            with patch('perception.live_slam.subprocess.Popen') as launch:
                with self.assertRaisesRegex(ValueError,'calibration differs'):
                    SlamProcess(Path(directory)/'output',calibration_path=calibration)
                launch.assert_not_called()

    def test_dataset_profile_is_passed_to_runner(self):
        from perception.vo import FR1_MATRIX,FR1_DISTORTION
        import io
        with TemporaryDirectory() as directory:
            calibration=Path(directory)/'tum.npz'
            np.savez(calibration,camera_matrix=FR1_MATRIX,distortion_coefficients=FR1_DISTORTION,image_size=[640,480])
            config=Path(__file__).resolve().parents[1]/'slam/tum_fr1_mono.yaml'
            process=SimpleNamespace(stdout=io.BytesIO(),poll=lambda:0)
            with patch('perception.live_slam.subprocess.Popen',return_value=process) as launch, \
                    patch('perception.live_slam.threading.Thread'), \
                    patch.object(SlamProcess,'receive',return_value={'ready':True}):
                bridge=SlamProcess(Path(directory)/'output',calibration_path=calibration,config_path=config)
                try:
                    from perception.live_slam import wsl_path
                    self.assertEqual(launch.call_args.args[0][-1],wsl_path(config))
                finally:bridge.close()

    def test_raw_transport_preserves_pixels_and_handles_short_writes(self):
        data=bytearray()
        class Pipe:
            def write(self,part):
                count=min(8191,len(part));data.extend(part[:count]);return count
        bridge=SlamProcess.__new__(SlamProcess);bridge.process=SimpleNamespace(stdin=Pipe())
        bridge.receive=lambda timeout:{'sequence':8,'timestamp':1.25}
        image=np.full((480,640,3),[0,10,255],np.uint8)
        result=bridge.feed_image(FramePacket(image,8,0),1.25)
        header,pixels=bytes(data).split(b'\n',1)
        self.assertEqual(header,b'FRAME 8 1.250000000 921600')
        self.assertEqual(pixels,image.tobytes())
        self.assertGreaterEqual(result['host_roundtrip_ms'],0)

    def test_tracking_loss_does_not_reuse_a_pose_or_dense_patch(self):
        matrix=np.array([[100.,0,50],[0,100.,50],[0,0,1]])
        reply={'sequence':1,'pose':None,'observed':[[0,0,2]],'sparse':[[1,2,3]]}
        points,colors,pose,status=live_cloud(reply,np.ones((100,100)),np.zeros((100,100,3),np.uint8),matrix,np.zeros(5))
        self.assertIsNone(pose)
        self.assertEqual(status['state'],'sparse_only')
        np.testing.assert_array_equal(points,[[1,2,3]])

    def test_supported_frame_generates_colored_local_points_in_world(self):
        matrix=np.array([[100.,0,50],[0,100.,50],[0,0,1]])
        u,v=np.meshgrid(np.arange(15,86,5),np.arange(15,86,5))
        uv=np.column_stack((u.ravel(),v.ravel()))
        inverse=0.5+uv[:,0]/100
        z=1/inverse
        camera=np.column_stack(((uv[:,0]-50)/100*z,(uv[:,1]-50)/100*z,z))
        pose=np.eye(4);pose[0,3]=2
        world=camera+pose[:3,3]
        prediction=np.tile(0.5+np.arange(100)/100,(100,1)).astype(np.float32)
        image=np.full((100,100,3),[10,20,30],np.uint8)
        reply={'sequence':4,'pose':pose.reshape(-1).tolist(),'observed':world.tolist(),'sparse':world[:3].tolist()}
        points,colors,actual,status=live_cloud(reply,prediction,image,matrix,np.zeros(5))
        self.assertEqual(status['state'],'local_dense_preview')
        self.assertGreater(status['dense_points'],100)
        self.assertLess(status['heldout_abs_rel_mean'],0.001)
        self.assertTrue(np.any(np.all(colors==[30,20,10],axis=1)))
        np.testing.assert_array_equal(actual,pose)

    def test_bad_alignment_keeps_only_sparse_points(self):
        pose=np.eye(4)
        reply={'sequence':4,'pose':pose.reshape(-1).tolist(),'observed':[],'sparse':[[0,0,2]]}
        points,_,_,status=live_cloud(reply,np.ones((100,100)),np.zeros((100,100,3),np.uint8),np.eye(3),np.zeros(5))
        self.assertEqual(len(points),1)
        self.assertEqual(status['state'],'sparse_only')
