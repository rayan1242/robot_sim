"""Inspect ordering on fixed geometric subsets; never changes fusion acceptance."""
import argparse
import json
from pathlib import Path

import msgpack
import numpy as np
from scipy.stats import spearmanr
from eval.diagnose_fusion import landmark_view_angles


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--map',type=Path,required=True)
    p.add_argument('--diagnostics',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();data=msgpack.unpackb(a.map.read_bytes(),raw=False,strict_map_key=False)
    angles=landmark_view_angles(data);meta=json.loads((a.diagnostics/'diagnostics.json').read_text())
    rows=[]
    with np.load(a.diagnostics/'correspondences.npz',allow_pickle=False) as arrays:
        indices=sorted(int(k.split('_')[-1]) for k in arrays.files if k.startswith('prediction_'))
        for index,view in zip(indices,meta['keyframes']):
            predicted=arrays[f'prediction_{index}'];inverse=arrays[f'inverse_depth_{index}']
            per_point=np.array([angles.get(int(i),0) for i in arrays[f'landmark_ids_{index}']])
            subsets=[]
            for threshold in [0,1,2,3,5]:
                keep=per_point>=threshold;count=int(keep.sum())
                correlation=float(spearmanr(predicted[keep],inverse[keep]).statistic) if count>=10 and np.ptp(predicted[keep])>1e-8 and np.ptp(inverse[keep])>1e-8 else None
                subsets.append({'min_estimated_max_ray_angle_degrees':threshold,'samples':count,'rank_correlation':correlation})
            rows.append({'timestamp':view['timestamp'],'subsets':subsets})
    report={'views':rows,'note':'Fixed diagnostic subsets only; no fit or held-out threshold tuning. Ray angles derive from estimated final SLAM geometry, not ground truth. Correlation needs at least 10 varied samples. Missing angle support receives zero.'}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2))
    print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
