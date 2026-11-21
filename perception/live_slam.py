"""Persistent WSL SLAM with bounded, latest-result delivery and exact frame pairing."""
import json
import io
from pathlib import Path
from collections import OrderedDict
from queue import Queue,Empty
import subprocess
import threading
import time

import cv2
import numpy as np

from .fusion import (fit_inverse_depth,project_landmarks,sample_bilinear,
                     alignment_support,backproject,voxel_downsample)


def wsl_path(path):
    value=Path(path).resolve().as_posix()
    return '/mnt/'+value[0].lower()+value[2:] if len(value)>2 and value[1]==':' else value


class SlamProcess:
    def __init__(self,directory,input_root=None,transport='raw',keyframes=False,calibration_path=None,config_path=None):
        if transport not in ('raw','png'):raise ValueError('Unknown SLAM transport')
        self.transport=transport
        self.keyframes=keyframes
        import yaml
        project=Path(__file__).resolve().parents[1]
        config_path=Path(config_path or project/'slam/webcam_640_mono.yaml').resolve()
        calibration_path=Path(calibration_path or project/'data/calibration.npz').resolve()
        config=yaml.safe_load(config_path.read_text())['Camera']
        with np.load(calibration_path,allow_pickle=False) as calibration:
            k=calibration['camera_matrix'];d=calibration['distortion_coefficients'].reshape(-1)
            actual=[k[0,0],k[1,1],k[0,2],k[1,2],*d[:5]]
            configured=[config[name] for name in ['fx','fy','cx','cy','k1','k2','p1','p2','k3']]
            if (tuple(calibration['image_size'])!=(640,480) or
                    (config['cols'],config['rows'])!=(640,480) or
                    not np.allclose(actual,configured,rtol=0,atol=1e-6)):
                raise ValueError('Saved calibration differs from SLAM configuration; update the profile before live mapping')
        self.directory=Path(directory).resolve();self.directory.mkdir(parents=True,exist_ok=True)
        self.messages=Queue(maxsize=2);self.closed=False
        self.log=(self.directory/'runner.log').open('w',encoding='utf-8')
        script=Path(__file__).resolve().parents[1]/'slam/run_live_wsl.sh'
        self.process=subprocess.Popen(['wsl','-d','Ubuntu','--','bash',wsl_path(script),wsl_path(input_root or self.directory),wsl_path(self.directory),wsl_path(config_path)],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.log,bufsize=0)
        self.reader=threading.Thread(target=self.read,daemon=True);self.reader.start()
        try:
            reply=self.receive(90)
            if not reply.get('ready'):raise RuntimeError('SLAM did not become ready')
        except Exception:self.close();raise

    def read(self):
        try:
            for line in io.BufferedReader(self.process.stdout,buffer_size=65536):
                if line.startswith(b'@@SLAM '):self.messages.put(json.loads(line[7:]))
            self.messages.put({'error':'Live SLAM process exited; inspect slam_input/runner.log'})
        except Exception as exc:self.messages.put({'error':str(exc)})

    def receive(self,timeout):
        try:reply=self.messages.get(timeout=timeout)
        except Empty:raise RuntimeError('Live SLAM timed out')
        if 'error' in reply:raise RuntimeError(reply['error'])
        return reply

    def feed(self,sequence,timestamp,filename):
        if any(c.isspace() for c in filename):raise ValueError('Relative frame path must not contain whitespace')
        suffix=' 1' if self.keyframes else ''
        self.write_all(f'{sequence} {timestamp:.9f} {filename}{suffix}\n'.encode())
        reply=self.receive(15)
        if reply.get('sequence')!=sequence or abs(reply.get('timestamp',-1)-timestamp)>1e-7:
            raise RuntimeError('SLAM frame/timestamp mismatch')
        return reply

    def write_all(self,data):
        view=memoryview(data)
        while view:
            count=self.process.stdin.write(view)
            if not count:raise RuntimeError('SLAM input pipe closed')
            view=view[count:]

    def feed_image(self,frame,timestamp):
        if frame.image.shape!=(480,640,3) or frame.image.dtype!=np.uint8:raise ValueError('Expected 640x480 uint8 BGR')
        started=time.perf_counter()
        payload=frame.image.tobytes(order='C')
        suffix=' 1' if getattr(self,'keyframes',False) else ''
        self.write_all(f'FRAME {frame.sequence} {timestamp:.9f} {len(payload)}{suffix}\n'.encode())
        self.write_all(payload)
        reply=self.receive(15)
        if reply.get('sequence')!=frame.sequence or abs(reply.get('timestamp',-1)-timestamp)>1e-7:raise RuntimeError('SLAM frame/timestamp mismatch')
        reply['host_roundtrip_ms']=(time.perf_counter()-started)*1000
        return reply

    def close(self):
        if self.closed:return
        self.closed=True
        try:
            if self.process.poll() is None:
                self.process.stdin.close();self.process.wait(timeout=15)
        except (OSError,subprocess.TimeoutExpired):self.process.kill();self.process.wait()
        self.reader.join(timeout=2);self.log.close()


class SlamCapture:
    def __init__(self,camera,bridge):
        self.camera=camera;self.bridge=bridge;self.origin=camera.get_latest().captured_at
        self.stop=threading.Event();self.condition=threading.Condition();self.latest=None;self.error=None
        self.archived=OrderedDict()
        (bridge.directory/'rgb').mkdir(exist_ok=True)
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()

    def run(self):
        sequence=-1
        try:
            with (self.bridge.directory/'rgb.txt').open('w') as index:
                while not self.stop.is_set():
                    frame=self.camera.get_latest(sequence);sequence=frame.sequence
                    filename=f'rgb/{sequence:08d}.png';timestamp=frame.captured_at-self.origin
                    selected_at=time.perf_counter()
                    write_ms=0
                    if self.bridge.transport=='png':
                        write_started=time.perf_counter()
                        if not cv2.imwrite(str(self.bridge.directory/filename),frame.image):raise RuntimeError('SLAM frame write failed')
                        write_ms=(time.perf_counter()-write_started)*1000
                        call_started=time.perf_counter();reply=self.bridge.feed(sequence,timestamp,filename)
                        reply['host_roundtrip_ms']=(time.perf_counter()-call_started)*1000
                    else:reply=self.bridge.feed_image(frame,timestamp)
                    reply['slam_frame_write_ms']=write_ms
                    reply['capture_to_slam_selection_ms']=(selected_at-frame.captured_at)*1000
                    reply['host_available_at']=time.perf_counter()
                    with self.condition:self.latest=(frame,reply);self.condition.notify_all()
                    if self.bridge.transport=='raw' and not cv2.imwrite(str(self.bridge.directory/filename),frame.image):raise RuntimeError('SLAM frame write failed')
                    with self.condition:
                        self.archived[round(timestamp,9)]=filename
                        while len(self.archived)>512:self.archived.popitem(last=False)
                    index.write(f'{timestamp:.9f} {filename}\n');index.flush()
        except Exception as exc:
            with self.condition:self.error=str(exc);self.condition.notify_all()

    def get_latest(self,sequence):
        with self.condition:
            ready=self.condition.wait_for(lambda:self.error or (self.latest and self.latest[0].sequence>sequence),timeout=20)
            if self.error:raise RuntimeError(self.error)
            if not ready:raise RuntimeError('No new live SLAM result')
            return self.latest

    def close(self):
        self.stop.set();self.thread.join(timeout=17)
        self.bridge.close()
        self.thread.join(timeout=2)

    def keyframe_image(self,timestamp):
        with self.condition:filename=self.archived.get(round(timestamp,9))
        return cv2.imread(str(self.bridge.directory/filename)) if filename else None


def live_cloud(reply,prediction,image,matrix,distortion):
    """Replace global sparse snapshot + local dense patch. Never accumulate stale poses."""
    sparse=np.asarray(reply.get('sparse',[]),dtype=float).reshape(-1,3)
    if not np.isfinite(sparse).all():raise ValueError('Nonfinite sparse map')
    colors=np.full(sparse.shape,160,dtype=np.uint8)
    status={'state':'sparse_only','reason':'No tracked pose','dense_history':'not accumulated; local patch replaced on each update'}
    if reply.get('pose') is None:return sparse,colors,None,status
    pose=np.asarray(reply['pose'],dtype=float).reshape(4,4)
    if not np.isfinite(pose).all():raise ValueError('Nonfinite pose')
    observed=np.asarray(reply.get('observed',[]),dtype=float).reshape(-1,3)
    depth,status=aligned_depth(observed,pose,prediction,matrix,distortion,reply['sequence'])
    if depth is not None:
        dense,rgb=backproject(depth,image,matrix,distortion,pose,stride=3)
        status['dense_points']=len(dense)
        sparse,colors=voxel_downsample(np.vstack([sparse,dense]),np.vstack([colors,rgb]),.002)
    status['dense_history']='not accumulated; local patch replaced on each update'
    return sparse,colors,pose,status


def aligned_depth(observed,pose,prediction,matrix,distortion,seed):
    status={'state':'sparse_only','reason':None}
    depth=None
    _,uv,z=project_landmarks(observed,pose,matrix,distortion,(prediction.shape[1],prediction.shape[0]))
    if len(z):
        order=np.argsort(z);_,unique=np.unique(np.round(uv[order]).astype(int),axis=0,return_index=True)
        uv,z=uv[order[unique]],z[order[unique]]
    try:
        if len(z)<70:raise ValueError('Fewer than 70 visible observed landmarks')
        sampled=sample_bilinear(prediction,uv);split=np.random.default_rng(seed).permutation(len(z))
        heldout,training=split[:max(8,len(z)//5)],split[max(8,len(z)//5):]
        fit=fit_inverse_depth(sampled[training],z[training])
        support,quality=alignment_support(fit,prediction,uv[training],sampled[training],z[training])
        status['quality']=quality
        if support is None:raise ValueError(quality['rejection'])
        depth=fit.depth(prediction);depth[~support]=np.nan
        depth[depth>float(np.percentile(z[training],95)*1.5)]=np.nan
        estimated=fit.depth(sampled[heldout]);valid=np.isfinite(estimated)
        errors=np.abs(estimated[valid]-z[heldout][valid])/z[heldout][valid]
        status.update(state='local_dense_preview',reason=None,quality=quality,
            heldout_samples=len(heldout),invalid_heldout=int((~valid).sum()),
            heldout_abs_rel_mean=float(errors.mean()) if len(errors) else None)
    except ValueError as exc:depth=None;status['reason']=str(exc)
    return depth,status
