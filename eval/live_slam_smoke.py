"""Exercise the persistent live protocol using saved RGB, without a physical camera."""
import json
import argparse
from pathlib import Path
import cv2
import numpy as np

from perception.live_slam import SlamProcess,live_cloud
from perception.depth import DepthEstimator
from fuse_dataset import load_camera,resize_intrinsics


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,default=Path('data/recordings/1793510972945292300'))
    parser.add_argument('--output',type=Path,default=Path('data/live_slam_protocol_smoke'))
    args=parser.parse_args();dataset=args.dataset
    output=args.output;output.mkdir(exist_ok=True)
    matrix,distortion,size=load_camera(Path('data/calibration.npz'),dataset)
    matrix=resize_intrinsics(matrix,size,(320,240))
    model=DepthEstimator(device='cpu',local_files_only=True)
    bridge=SlamProcess(output,input_root=dataset)
    rows=[s.split() for s in (dataset/'rgb.txt').read_text().splitlines() if s.strip() and not s.startswith('#')]
    poses=0;updates=[];first=None
    try:
        for sequence,(timestamp,filename) in enumerate(rows):
            reply=bridge.feed(sequence,float(timestamp),filename)
            if reply['pose'] is not None:
                poses+=1
                if first is None:first=sequence
                if poses%30==1:
                    image=cv2.resize(cv2.imread(str(dataset/filename)),(320,240),interpolation=cv2.INTER_AREA)
                    predicted=model.predict(image)
                    points,colors,pose,status=live_cloud(reply,predicted,image,matrix,distortion)
                    np.savez_compressed(output/f'cloud_{sequence:04d}.npz',points=points,rgb=colors)
                    updates.append({'sequence':sequence,'points':len(points),'fusion':status})
            if sequence%50==0:print(f'Fed {sequence+1}/{len(rows)}; tracked {poses}',flush=True)
    finally:bridge.close()
    report={'input_frames':len(rows),'tracked_frames':poses,'first_pose_sequence':first,'updates':updates,
        'note':'Persistent live process tested on saved RGB with exact timestamps; not a live camera performance benchmark'}
    (output/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    if not poses or not any(u['points']>0 for u in updates):raise RuntimeError('No tracked point-cloud updates')


if __name__=='__main__':main()
