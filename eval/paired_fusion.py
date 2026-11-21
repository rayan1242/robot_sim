"""Paired offline ablation of selection and cross-view validation. No live defaults change."""
import argparse
import json
from pathlib import Path

import cv2
import msgpack
import numpy as np

from eval.diagnose_fusion import audit_keyframe
from fuse_dataset import load_camera,resize_intrinsics
from perception.depth import DepthEstimator
from perception.fusion import (project_landmarks,sample_bilinear,fit_inverse_depth,
    alignment_support,backproject,multiview_support,voxel_downsample)
from perception.keyframes import select_keyframes


CASES={'successful':'79c2df1975674ee6bfce9c3f2bad374f','rejected':'93601a495a6147a88e625fa1f03345c9'}


def fit_view(key,data,image,prediction,matrix,distortion,original_matrix,index):
    pose,observed,_=audit_keyframe(key,data['landmarks'],original_matrix)
    _,uv,z=project_landmarks(observed,pose,matrix,distortion,(prediction.shape[1],prediction.shape[0]))
    order=np.argsort(z)
    if len(order):
        _,unique=np.unique(np.round(uv[order]).astype(int),axis=0,return_index=True)
        uv,z=uv[order[unique]],z[order[unique]]
    row={'timestamp':key['ts'],'visible_landmarks':len(z)}
    if len(z)<70:return None,{**row,'status':'insufficient_landmarks'}
    values=sample_bilinear(prediction,uv);split=np.random.default_rng(index).permutation(len(z));n=max(8,len(z)//5)
    heldout,training=split[:n],split[n:]
    try:fit=fit_inverse_depth(values[training],z[training],seed=index)
    except ValueError as exc:return None,{**row,'status':'fit_failed','reason':str(exc)}
    estimated=fit.depth(values[heldout]);valid=np.isfinite(estimated)
    errors=np.abs(estimated[valid]-z[heldout][valid])/z[heldout][valid]
    row.update(scale=fit.scale,shift=fit.shift,heldout_valid=len(errors),heldout_invalid=int((~valid).sum()),
        heldout_abs_rel_mean=float(errors.mean()) if len(errors) else None)
    support,quality=alignment_support(fit,prediction,uv[training],values[training],z[training]);row['quality']=quality
    if support is None:return None,{**row,'status':'quality_rejected','reason':quality['rejection']}
    depth=fit.depth(prediction);depth[~support]=np.nan
    points,colors=backproject(depth,image,matrix,distortion,pose,stride=3,max_depth=float(np.percentile(z[training],95)*1.5))
    return {'pose':pose,'depth':depth,'points':points,'rgb':colors,'errors':errors},dict(row,status='supported')


def build_variant(selected,cross_view,matrix,distortion,output):
    views=[(e['fit']['pose'],e['fit']['depth']) for e in selected]
    chunks=[];colors=[];checks=[];errors=[];raw=0
    for index,e in enumerate(selected):
        fit=e['fit'];points=fit['points'];rgb=fit['rgb'];raw+=len(points);errors.extend(fit['errors'].tolist())
        if cross_view:
            keep,stats=multiview_support(points,index,views,matrix,distortion)
            points,rgb=points[keep],rgb[keep];checks.append({'timestamp':e['timestamp'],**stats})
        if len(points):chunks.append(points);colors.append(rgb)
    after=sum(len(p) for p in chunks)
    summary={'selected_supported_views':len(selected),'views_with_output_points':len(chunks),
        'candidate_points':raw,'points_before_voxelization':after,'retained_candidate_fraction':after/raw if raw else None,
        'heldout_valid_before_cross_view':len(errors),'heldout_abs_rel_mean_before_cross_view':float(np.mean(errors)) if errors else None,
        'cross_view_checks':checks,'voxelized_points':0}
    if chunks:
        points,rgb=voxel_downsample(np.vstack(chunks),np.vstack(colors),.002)
        np.savez_compressed(output,points=points,rgb=rgb);summary['voxelized_points']=len(points)
    return summary


def run_case(name,session,model,root,output):
    source=root/session/'slam_input';output.mkdir(parents=True,exist_ok=True)
    data=msgpack.unpackb((source/'map.msg').read_bytes(),raw=False,strict_map_key=False)
    keys=sorted(data['keyframes'].values(),key=lambda k:k['ts'])
    original,distortion,size=load_camera(Path('data/calibration.npz'),source)
    matrix=resize_intrinsics(original,size,(224,168))
    rows=[s.split() for s in (source/'rgb.txt').read_text().splitlines() if s.strip() and not s.startswith('#')]
    times=np.array([float(r[0]) for r in rows]);prepared=[];sharpness={}
    for index,key in enumerate(keys):
        i=int(np.argmin(abs(times-key['ts'])))
        if abs(times[i]-key['ts'])>.001:raise ValueError('Missing exact keyframe image')
        path=(source/rows[i][1]).resolve()
        if not path.is_relative_to(source.resolve()):raise ValueError('RGB path escapes source')
        original_image=cv2.imread(str(path))
        if original_image is None or (original_image.shape[1],original_image.shape[0])!=size:raise ValueError('Invalid RGB dimensions')
        sharp=cv2.resize(original_image,(320,240),interpolation=cv2.INTER_AREA)
        sharpness[key['ts']]=float(cv2.Laplacian(cv2.cvtColor(sharp,cv2.COLOR_BGR2GRAY),cv2.CV_64F).var())
        image=cv2.resize(original_image,(224,168),interpolation=cv2.INTER_AREA)
        prediction=model.predict(image)
        fit,row=fit_view(key,data,image,prediction,matrix,distortion,original,index)
        prepared.append({'timestamp':key['ts'],'fit':fit,'report':row})
        print(f'{name}: evaluated {index+1}/{len(keys)} retained views',flush=True)
    chosen,decisions=select_keyframes(keys,data['landmarks'],sharpness)
    chosen_times={k['ts'] for k in chosen}
    supported=[e for e in prepared if e['fit'] is not None]
    selected=[e for e in supported if e['timestamp'] in chosen_times]
    variants={}
    for label,entries,cross_view in [('all',supported,False),('selected',selected,False),('all_multiview',supported,True),('selected_multiview',selected,True)]:
        variants[label]=build_variant(entries,cross_view,matrix,distortion,output/(label+'.npz'))
    report={'session':session,'retained_keyframes':len(keys),'selected_keyframes_before_depth_acceptance':len(chosen),
        'depth_supported_views':len(supported),'selection':decisions,'per_view':[e['report'] for e in prepared],'variants':variants,
        'note':'All variants reuse identical per-view predictions, fits and train/test splits. Selection never uses depth errors. Cross-view filtering changes coverage, not those depth estimates.'}
    (output/'report.json').write_text(json.dumps(report,indent=2))
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path('data/sessions'))
    p.add_argument('--output',type=Path,default=Path('data/paired_fusion'))
    a=p.parse_args()
    if a.output.exists():raise ValueError('Use a fresh experiment output directory')
    a.output.mkdir(parents=True)
    model=DepthEstimator(device='cpu',local_files_only=True)
    reports={name:run_case(name,session,model,a.root,a.output/name) for name,session in CASES.items()}
    summary={'policy':{'input_wh':[224,168],'min_shared_landmarks':70,'min_pair_angle_degrees':1,
        'min_laplacian_variance_320x240':50,'other_view_depth_tolerance':.1,'min_supporting_other_views':1,'voxel_size_arbitrary_units':.002},
        'cases':{name:{k:r[k] for k in ['session','retained_keyframes','selected_keyframes_before_depth_acceptance','depth_supported_views','variants']} for name,r in reports.items()},
        'limitations':['Offline final optimized geometry, not a live performance experiment',
            'Two previously investigated examples, not an unseen validation set',
            'Selection sharpness/shared-count thresholds are fixed engineering heuristics, not calibrated confidence',
            'No ground truth: retained points and agreement are consistency/coverage, not independent accuracy',
            'Selection changes view coverage; cross-view filtering does not improve identical estimates',
            'No live defaults or fusion acceptance thresholds changed']}
    (a.output/'summary.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps({name:{k:v['voxelized_points'] for k,v in r['variants'].items()} for name,r in reports.items()},indent=2))


if __name__=='__main__':main()
