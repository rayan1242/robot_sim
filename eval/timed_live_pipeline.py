"""Run the real live worker on timed saved RGB with a latest-frame capture slot.

No physical camera: preserves asynchronous SLAM/depth scheduling under timed input.
"""
import argparse
import json
from pathlib import Path
from queue import Queue
import threading
import time
from unittest.mock import patch

import cv2

from backend.worker import camera_worker
from perception.capture import FramePacket


class TimedCamera:
    def __init__(self,dataset,**kwargs):
        self.dataset=dataset;self.rows=[r.split() for r in (dataset/'rgb.txt').read_text().splitlines() if r.strip() and not r.startswith('#')]
        self.condition=threading.Condition();self.stop=threading.Event();self.frame=None
        self.settings={'backend':'TIMED_SAVED_RGB','note':'Not a physical webcam test'}
        self.capture_fps=(len(self.rows)-1)/(float(self.rows[-1][0])-float(self.rows[0][0]))
    def run(self):
        started=time.perf_counter();origin=float(self.rows[0][0])
        for sequence,(timestamp,filename) in enumerate(self.rows):
            if self.stop.wait(max(0,started+float(timestamp)-origin-time.perf_counter())):break
            image=cv2.imread(str(self.dataset/filename));image.flags.writeable=False
            with self.condition:self.frame=FramePacket(image,sequence,time.perf_counter());self.condition.notify_all()
        while not self.stop.wait(1/self.capture_fps):
            with self.condition:
                self.frame=FramePacket(self.frame.image,self.frame.sequence+1,time.perf_counter());self.condition.notify_all()
    def get_latest(self,after_sequence=-1):
        with self.condition:
            if not self.condition.wait_for(lambda:self.frame is not None and self.frame.sequence>after_sequence,timeout=10):raise RuntimeError('Timed input stalled')
            return self.frame
    def __enter__(self):
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start();self.get_latest();return self
    def __exit__(self,*args):self.stop.set();self.thread.join()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,default=Path('data/recordings/1793498406555488000'))
    p.add_argument('--duration',type=float,default=22)
    p.add_argument('--output',type=Path,default=Path('data/timed_live_pipeline'))
    p.add_argument('--transport',choices=['raw','png'],default='raw')
    p.add_argument('--depth-width',type=int,choices=[160,224,320],default=320)
    p.add_argument('--keyframe-map',action='store_true')
    p.add_argument('--tum-profile',action='store_true',help='Use Freiburg calibration for the original TUM xyz dataset only')
    p.add_argument('--initializer-profile',choices=['baseline','strict'],default='baseline')
    a=p.parse_args()
    if a.tum_profile and a.dataset.resolve()!=Path('data/rgbd_dataset_freiburg1_xyz').resolve():
        p.error('--tum-profile requires the original local TUM xyz dataset')
    if a.tum_profile and a.initializer_profile!='baseline':p.error('Webcam strict profile cannot be used with TUM')
    rows=[r.split() for r in (a.dataset/'rgb.txt').read_text().splitlines() if r.strip() and not r.startswith('#')]
    available=float(rows[-1][0])-float(rows[0][0])
    if a.duration<=0 or a.duration>=available:p.error('Duration must be positive and shorter than the source sequence')
    a.output.mkdir(parents=True,exist_ok=False)
    profile={}
    if a.initializer_profile=='strict':
        profile={'slam_config':'slam/webcam_640_mono_strict.yaml','slam_initialization_profile':'strict'}
    if a.tum_profile:
        import numpy as np
        from perception.vo import FR1_MATRIX,FR1_DISTORTION
        calibration=a.output/'tum_calibration.npz'
        np.savez(calibration,camera_matrix=FR1_MATRIX,distortion_coefficients=FR1_DISTORTION,image_size=[640,480])
        profile={'slam_calibration':str(calibration),'slam_config':'slam/tum_fr1_mono.yaml'}
    (a.output/'trial_config.json').write_text(json.dumps({'dataset':str(a.dataset),'duration':a.duration,'depth_width':a.depth_width,
        'keyframe_map':a.keyframe_map,'transport':a.transport,'profile':profile,'source':'Timed saved RGB; not physical webcam'},indent=2))
    class LocalQueue(Queue):
        def close(self):pass
        def join_thread(self):pass
    with patch('perception.capture.CameraCapture',side_effect=lambda **kwargs:TimedCamera(a.dataset,**kwargs)):
        camera_worker(a.output,{'slam':True,'keyframe_map':a.keyframe_map,'slam_transport':a.transport,'depth':True,'device':'cpu','camera':0,'width':640,'height':480,
            'fps':15,'backend':'dshow','duration':a.duration,'depth_width':a.depth_width,'depth_height':a.depth_width*3//4,**profile},LocalQueue(maxsize=1),threading.Event())
    if (a.output/'error.txt').exists():raise RuntimeError((a.output/'error.txt').read_text())
    states=[json.loads(s) for s in (a.output/'states.jsonl').read_text().splitlines()]
    result={'source':'Timed saved RGB, not physical webcam','worker_outputs':len(states),
        'outputs_with_pose':sum(s['pose'] is not None for s in states),
        'outputs_with_dense_preview':sum(s.get('fusion',{}).get('state')=='local_dense_preview' for s in states),
        'outputs_with_keyframe_window':sum(s.get('fusion',{}).get('state')=='keyframe_window' for s in states),
        'exact_frame_matches':all(abs(s['slam_timestamp']-s['timestamp'])<1e-7 and s['slam_sequence']==s['capture_sequence'] for s in states),
        'final_map_points':len(__import__('numpy').load(a.output/'map.npz')['points'])}
    (a.output/'verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
    if not result['outputs_with_pose']:raise RuntimeError('No tracked outputs in timed test')


if __name__=='__main__':main()
