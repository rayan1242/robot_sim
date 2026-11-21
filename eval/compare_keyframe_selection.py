"""Compare policies against one frozen SLAM trace and shared depth predictions."""
import argparse
import hashlib
import json
from pathlib import Path

import cv2
import numpy as np

from fuse_dataset import load_camera,resize_intrinsics
from perception.depth import DepthEstimator
from perception.keyframe_window import ActiveKeyframeWindow
from perception.live_slam import SlamProcess


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--stride',type=int,default=8)
    p.add_argument('--trace',type=Path,help='Reuse an existing trace instead of running SLAM')
    p.add_argument('--compare-windows',action='store_true',help='Compare newest/diverse windows with all-cached candidate selection')
    a=p.parse_args()
    if a.stride<1:p.error('Stride must be positive')
    a.output.mkdir(parents=True,exist_ok=False)
    rows=[r.split() for r in (a.dataset/'rgb.txt').read_text().splitlines() if r.strip() and not r.startswith('#')]
    trace=a.trace or a.output/'snapshots.jsonl'
    if a.trace is None:
        bridge=SlamProcess(a.output/'slam',input_root=a.dataset,keyframes=True,config_path='slam/webcam_640_mono_strict.yaml')
        try:
            with trace.open('w') as f:
                for seq,(ts,name) in enumerate(rows):
                    reply=bridge.feed(seq,float(ts),name)
                    if seq%a.stride==0 or seq==len(rows)-1:f.write(json.dumps(reply)+'\n')
        finally:bridge.close()
    matrix,dist,size=load_camera(Path('data/calibration.npz'),a.dataset)
    matrix=resize_intrinsics(matrix,size,(224,168))
    images={round(float(ts),9):name for ts,name in rows}
    model=DepthEstimator(device='cpu',local_files_only=True)
    if a.compare_windows:
        windows={policy:ActiveKeyframeWindow(window_policy=policy) for policy in ['newest','diverse']}
    else:
        # Keep the original candidate-selection experiment's newest-only window.
        windows={policy:ActiveKeyframeWindow(selection_policy=policy,window_policy='newest') for policy in ['newest','all_cached']}
    predictions={};metrics={policy:[] for policy in windows}
    (a.output/'predictions').mkdir()
    with trace.open() as f:
        for line in f:
            reply=json.loads(line)
            def load(ts):
                if ts>reply['timestamp']+1e-7:return None
                name=images.get(round(ts,9))
                if name is None:return None
                path=(a.dataset/name).resolve()
                if not path.is_relative_to(a.dataset.resolve()):raise ValueError('Image escapes dataset')
                return cv2.imread(str(path))
            def predict(image):
                key=hashlib.sha256(image.tobytes()).hexdigest()
                if key not in predictions:
                    predictions[key]=model.predict(image).copy()
                    np.save(a.output/'predictions'/f'{key}.npy',predictions[key])
                return predictions[key].copy()
            for policy,window in windows.items():
                before=len(predictions)
                points,colors,pose,status=window.update(reply,load,predict,matrix,dist,(224,168))
                metrics[policy].append({'timestamp':reply['timestamp'],'posed':pose is not None,
                    'status':status,'points':len(points),'new_shared_predictions':len(predictions)-before})
    summary={}
    for policy,records in metrics.items():
        dense=[r for r in records if r['status']['dense_points']>0]
        summary[policy]={'outputs':len(records),'posed_outputs':sum(r['posed'] for r in records),
            'dense_outputs':len(dense),'first_dense':dense[0]['timestamp'] if dense else None,
            'cached_prediction_events':sum(r['status']['new_keyframe_id'] is not None for r in records),
            'max_cache':max(r['status']['prediction_cache_size'] for r in records),
            'max_dense':max(r['status']['dense_points'] for r in records)}
        (a.output/f'{policy}.json').write_text(json.dumps(records,indent=2))
    report={'dataset':str(a.dataset),'trace':str(trace),'source_frames':len(rows),'snapshot_stride':a.stride,
        'unique_model_predictions':len(predictions),'policies':summary,'compare_windows':a.compare_windows,
        'note':'Same frozen online SLAM replies and pixel-identical shared predictions. Saved-input SLAM and fixed snapshot decimation, not original live scheduling or a latency benchmark. Quality gates unchanged.'}
    (a.output/'comparison.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))


if __name__=='__main__':main()
