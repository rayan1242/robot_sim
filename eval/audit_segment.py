"""Measure neighboring-view agreement in a fixed, already-fused segment."""
import argparse
import csv
import json
from pathlib import Path

import cv2
import msgpack
import numpy as np
from scipy.spatial.transform import Rotation

from fuse_dataset import load_camera, resize_intrinsics
from perception.depth import DepthEstimator
from perception.fusion import DepthAlignment, backproject, project_landmarks, sample_bilinear


def pair_agreement(points, colors, target_pose, target_depth, target_image, matrix, distortion):
    ids,uv,z=project_landmarks(points,target_pose,matrix,distortion,(target_depth.shape[1],target_depth.shape[0]))
    other=sample_bilinear(target_depth,uv)
    valid=np.isfinite(other)&(other>0)
    relative=np.abs(z[valid]-other[valid])/other[valid]
    transferred=np.column_stack([sample_bilinear(target_image[:,:,c],uv[valid]) for c in range(3)])
    rgb_error=np.abs(transferred[:,::-1]-colors[ids[valid]].astype(float)).mean(axis=1)
    return {'projected_samples':int(len(ids)),'valid_samples':int(valid.sum()),
        'depth_abs_rel_median':float(np.median(relative)) if len(relative) else None,
        'depth_abs_rel_p90':float(np.percentile(relative,90)) if len(relative) else None,
        'fraction_within_10_percent':float(np.mean(relative<=0.1)) if len(relative) else None,
        'rgb_transfer_mean_abs_error_0_255':float(np.mean(rgb_error)) if len(rgb_error) else None}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,default=Path('data/recordings/1793498406555488000'))
    p.add_argument('--slam',type=Path,default=Path('data/slam_webcam_1793498406555488000'))
    p.add_argument('--fusion',type=Path,default=Path('data/fusion_webcam_multiview/report.json'))
    p.add_argument('--calibration',type=Path,default=Path('data/calibration.npz'))
    p.add_argument('--start',type=float,default=14)
    p.add_argument('--end',type=float,default=20.1)
    p.add_argument('--output',type=Path,default=Path('docs/fusion_diagnostics/segment'))
    a=p.parse_args()
    if a.end<=a.start:p.error('end must exceed start')
    report=json.loads(a.fusion.read_text())
    fits=[r for r in report['keyframes'] if r['status']=='fused' and a.start<=r['timestamp']<=a.end]
    if len(fits)<2:raise ValueError('Need at least two already-fused keyframes')
    raw,distortion,size=load_camera(a.calibration,a.dataset);matrix=resize_intrinsics(raw,size,(320,240))
    poses=np.loadtxt(a.slam/'keyframe_trajectory.txt',ndmin=2)
    rgb=[s.split() for s in (a.dataset/'rgb.txt').read_text().splitlines() if s.strip() and not s.startswith('#')]
    times=np.array([float(r[0]) for r in rgb])
    print(f'Auditing {len(fits)} keyframes; loading cached depth model',flush=True)
    model=DepthEstimator(device='cpu',local_files_only=True)
    views=[];images=[]
    for fit in fits:
        ts=fit['timestamp'];i=int(np.argmin(abs(times-ts)))
        if abs(times[i]-ts)>0.001:raise ValueError('No exact RGB timestamp match')
        path=(a.dataset/rgb[i][1]).resolve()
        if not path.is_relative_to(a.dataset.resolve()):raise ValueError('RGB path escapes dataset')
        image=cv2.imread(str(path))
        if image is None or (image.shape[1],image.shape[0])!=size:raise ValueError('Invalid RGB')
        image=cv2.resize(image,(320,240),interpolation=cv2.INTER_AREA)
        prediction=model.predict(image)
        depth=DepthAlignment(fit['inverse_depth_scale'],fit['inverse_depth_shift'],0,0).depth(prediction)
        quality=fit.get('quality',{})
        depth[(prediction<quality.get('prediction_support_min',-np.inf))|(prediction>quality.get('prediction_support_max',np.inf))]=np.nan
        row=poses[np.argmin(abs(poses[:,0]-ts))]
        if abs(row[0]-ts)>0.001:raise ValueError('No exact keyframe pose match')
        pose=np.eye(4);pose[:3,:3]=Rotation.from_quat(row[4:8]).as_matrix();pose[:3,3]=row[1:4]
        views.append((pose,depth,image));preview=image.copy()
        cv2.putText(preview,f't={ts:.2f}s',(8,22),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,255,0),1)
        images.append(preview)
        print(f'Prepared audit view at {ts:.3f}s',flush=True)
    pairs=[]
    for i in range(len(views)-1):
        for source,target in [(i,i+1),(i+1,i)]:
            pose,depth,image=views[source];target_pose,target_depth,target_image=views[target]
            points,colors=backproject(depth,image,matrix,distortion,pose,stride=6)
            result=pair_agreement(points,colors,target_pose,target_depth,target_image,matrix,distortion)
            result.update(source_timestamp=fits[source]['timestamp'],target_timestamp=fits[target]['timestamp'])
            pairs.append(result)
    with (a.slam/'tracking.csv').open() as handle:
        tracked=[r for r in csv.DictReader(handle) if a.start<=float(r['timestamp'])<=a.end]
    data=msgpack.unpackb((a.slam/'map.msg').read_bytes(),raw=False,strict_map_key=False)
    selected=[k for k in data['keyframes'].values() if a.start<=k['ts']<=a.end]
    angles=[]
    for first,second in zip(sorted(selected,key=lambda k:k['ts']),sorted(selected,key=lambda k:k['ts'])[1:]):
        centers=[]
        for key in [first,second]:centers.append(-Rotation.from_quat(key['rot_cw']).as_matrix().T@np.array(key['trans_cw']))
        for identifier in set(first['lm_ids'])&set(second['lm_ids']):
            landmark=data['landmarks'].get(str(identifier))
            if landmark is None:continue
            u=np.array(landmark['pos_w'])-centers[0];v=np.array(landmark['pos_w'])-centers[1]
            norm=np.linalg.norm(u)*np.linalg.norm(v)
            if norm>1e-12:angles.append(float(np.degrees(np.arccos(np.clip(u@v/norm,-1,1)))))
    result={'interval_seconds':[a.start,a.end],'available_pose_frames':sum(int(r['pose_available']) for r in tracked),
        'input_frames':len(tracked),'fused_keyframes':len(fits),
        'shared_landmark_neighbor_ray_angle_median_degrees':float(np.median(angles)) if angles else None,
        'neighbor_landmark_pairs':len(angles),'pairs':pairs,
        'limitations':['Uses saved optimized poses and existing fits; no new fitting or threshold tuning',
            'Range-limited depth support; not the training convex-hull mask',
            'Pair errors include occlusions and view-dependent predictions; they are not independent accuracy',
            'Photometric error includes exposure changes and occlusion; not an isolated pose test',
            'Internal landmark ray angles are estimates, not measured physical baselines']}
    a.output.mkdir(parents=True,exist_ok=True)
    (a.output/'report.json').write_text(json.dumps(result,indent=2))
    cv2.imwrite(str(a.output/'frames.jpg'),np.hstack(images))
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
