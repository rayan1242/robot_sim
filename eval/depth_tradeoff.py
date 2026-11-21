"""Small repeated-input CPU experiment, with identical sparse train/test samples."""
import json
import argparse
import platform
from pathlib import Path

import cv2
import msgpack
import numpy as np

from eval.diagnose_fusion import audit_keyframe
from fuse_dataset import load_camera,resize_intrinsics
from perception.depth import DepthEstimator
from perception.fusion import project_landmarks,sample_bilinear,fit_inverse_depth,alignment_support
from perception.timing import distribution


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,default=Path('data/recordings/1793498406555488000'))
    p.add_argument('--slam',type=Path,default=Path('data/slam_webcam_1793498406555488000'))
    p.add_argument('--start',type=float,default=14);p.add_argument('--end',type=float,default=20.1)
    p.add_argument('--max-views',type=int,default=5);p.add_argument('--repeats',type=int,default=6)
    p.add_argument('--output',type=Path,default=Path('data/depth_tradeoff'))
    a=p.parse_args()
    if a.repeats<1 or a.max_views<1 or a.end<=a.start:p.error('Invalid experiment bounds')
    dataset=a.dataset;slam=a.slam
    matrix,distortion,size=load_camera(Path('data/calibration.npz'),dataset)
    small=resize_intrinsics(matrix,size,(320,240))
    data=msgpack.unpackb((slam/'map.msg').read_bytes(),raw=False,strict_map_key=False)
    rows=[s.split() for s in (dataset/'rgb.txt').read_text().splitlines() if s.strip() and not s.startswith('#')]
    times=np.array([float(r[0]) for r in rows]);views=[]
    selected=[k for k in sorted(data['keyframes'].values(),key=lambda k:k['ts']) if a.start<=k['ts']<=a.end]
    if len(selected)>a.max_views:selected=[selected[i] for i in np.linspace(0,len(selected)-1,a.max_views,dtype=int)]
    for key in selected:
        pose,points,_=audit_keyframe(key,data['landmarks'],matrix)
        _,uv,z=project_landmarks(points,pose,small,distortion,(320,240))
        keep=(uv[:,0]>2)&(uv[:,0]<317)&(uv[:,1]>2)&(uv[:,1]<237);uv,z=uv[keep],z[keep]
        split=np.random.default_rng(123).permutation(len(z));n=max(8,len(z)//5)
        i=int(np.argmin(abs(times-key['ts'])))
        if abs(times[i]-key['ts'])>.001:raise ValueError('Missing exact RGB timestamp')
        path=(dataset/rows[i][1]).resolve()
        if not path.is_relative_to(dataset.resolve()):raise ValueError('RGB path escapes dataset')
        image=cv2.imread(str(path))
        views.append((image,uv,z,split[n:],split[:n],key['ts']))
    if not views:raise ValueError('No selected keyframes')
    model=DepthEstimator(device='cpu',local_files_only=True)
    cases=[(160,120),(224,168),(320,240)]
    output={str(w):{'input_size_wh':[w,h],'timings':[],'heldout_errors':[],'invalid_heldout':0,'failed_fits':0,'per_view':[],'quality_rejections':0} for w,h in cases}
    for w,h in cases:model.predict(cv2.resize(views[0][0],(w,h),interpolation=cv2.INTER_AREA))
    for repeat in range(a.repeats):
        for image,uv,z,training,heldout,timestamp in views:
            for w,h in cases[repeat%3:]+cases[:repeat%3]:
                predicted=model.predict(cv2.resize(image,(w,h),interpolation=cv2.INTER_AREA))
                result=output[str(w)];result['timings'].append(model.last_timings['total_ms'])
                if repeat:continue
                coords=(uv+.5)*np.array([w/320,h/240])-.5
                values=sample_bilinear(predicted,coords)
                try:fit=fit_inverse_depth(values[training],z[training])
                except ValueError as exc:
                    result['failed_fits']+=1;result['per_view'].append({'timestamp':timestamp,'status':'fit_failed','reason':str(exc)});continue
                estimate=fit.depth(values[heldout]);valid=np.isfinite(estimate)
                result['invalid_heldout']+=int((~valid).sum())
                result['heldout_errors'].extend((np.abs(estimate[valid]-z[heldout][valid])/z[heldout][valid]).tolist())
                support,quality=alignment_support(fit,predicted,coords[training],values[training],z[training])
                if support is None:result['quality_rejections']+=1
                result['per_view'].append({'timestamp':timestamp,'status':'supported' if support is not None else 'quality_rejected',
                    'quality':quality,'heldout_valid':int(valid.sum()),'heldout_invalid':int((~valid).sum()),
                    'heldout_abs_rel_mean':float(np.mean(np.abs(estimate[valid]-z[heldout][valid])/z[heldout][valid])) if valid.any() else None})
        print(f'Completed repeat {repeat+1}/{a.repeats}',flush=True)
    for r in output.values():
        r['processing']=distribution(r.pop('timings'))
        errors=r.pop('heldout_errors');r['heldout_samples']=len(errors)
        r['heldout_abs_rel_mean']=float(np.mean(errors)) if errors else None
    report={'platform':platform.platform(),'processor':platform.processor(),'torch_threads':model.torch.get_num_threads(),
        'dataset':str(dataset),'slam':str(slam),'selected_views':len(views),'repeats':a.repeats,
        'model':model.model_id,'device':'cpu','precision':'fp32','cases':output,
        'scope':f'{len(views)*a.repeats} timing samples per size: {len(views)} identical saved keyframes repeated {a.repeats} times, rotating variant order; one warmup per size excluded. Model predict timing excludes disk, explicit input resize, capture, network and browser. Mean agreement includes all fitted views, including quality-rejected views.',
        'quality_note':'Same per-view sparse train/test samples at each size, no thresholds tuned. SLAM agreement is not independent accuracy. Repeated images do not add independent quality samples. Small selected scene; not a generalization benchmark. Background load and power mode uncontrolled.'}
    path=a.output;path.mkdir(parents=True,exist_ok=True)
    (path/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))


if __name__=='__main__':main()
