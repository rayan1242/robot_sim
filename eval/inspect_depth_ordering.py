"""Spatial diagnostics of saved keyframe depth ordering; never changes fusion."""
import argparse
import json
from pathlib import Path

import cv2
import msgpack
import numpy as np
from scipy.stats import rankdata, spearmanr

from eval.diagnose_fusion import audit_keyframe
from fuse_dataset import load_camera, resize_intrinsics
from perception.depth import DepthEstimator
from perception.fusion import project_landmarks, sample_bilinear


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dataset',type=Path,required=True)
    p.add_argument('--slam',type=Path,required=True)
    p.add_argument('--calibration',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    raw,dist,size=load_camera(a.calibration,a.dataset)
    matrix=resize_intrinsics(raw,size,(224,168))
    data=msgpack.unpackb((a.slam/'map.msg').read_bytes(),raw=False,strict_map_key=False)
    keys=sorted(data['keyframes'].values(),key=lambda x:x['ts'])
    rows=[r.split() for r in (a.dataset/'rgb.txt').read_text().splitlines() if r.strip() and not r.startswith('#')]
    times=np.array([float(r[0]) for r in rows])
    model=DepthEstimator(device='cpu',local_files_only=True)
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    report=[]
    for index in np.unique(np.linspace(0,len(keys)-1,3,dtype=int)):
        key=keys[index];i=int(np.argmin(abs(times-key['ts'])))
        if abs(times[i]-key['ts'])>1e-6:raise ValueError('Missing exact keyframe image')
        path=(a.dataset/rows[i][1]).resolve()
        if not path.is_relative_to(a.dataset.resolve()):raise ValueError('Image escapes dataset')
        image=cv2.imread(str(path))
        if image is None or (image.shape[1],image.shape[0])!=size:raise ValueError('Invalid image')
        image=cv2.resize(image,(224,168),interpolation=cv2.INTER_AREA)
        predicted=model.predict(image)
        pose,points,residuals=audit_keyframe(key,data['landmarks'],raw)
        ids,uv,z=project_landmarks(points,pose,matrix,dist,(224,168))
        values=sample_bilinear(predicted,uv)
        valid=np.isfinite(values)&np.isfinite(z)&(z>0)
        uv,z,values=uv[valid],z[valid],values[valid]
        inverse=1/z
        model_rank=rankdata(values)/len(values);slam_rank=rankdata(inverse)/len(inverse)
        # Fixed image cells localize ordering disagreements without semantic labels.
        cells=[]
        for row in range(3):
            for col in range(4):
                mask=(uv[:,0]>=col*56)&(uv[:,0]<(col+1)*56)&(uv[:,1]>=row*56)&(uv[:,1]<(row+1)*56)
                cells.append({'row':row,'column':col,'samples':int(mask.sum()),
                    'median_model_nearness_percentile':float(np.median(model_rank[mask])) if mask.any() else None,
                    'median_slam_nearness_percentile':float(np.median(slam_rank[mask])) if mask.any() else None,
                    'local_rank_correlation':float(spearmanr(values[mask],inverse[mask]).statistic) if mask.sum()>=10 else None})
        entry={'timestamp':key['ts'],'samples':len(z),'rank_correlation':float(spearmanr(values,inverse).statistic),
            'reprojection_median_px':float(np.median(residuals)),'cells':cells}
        report.append(entry)
        np.savez_compressed(a.output/f'view_{index}.npz',uv=uv,slam_z=z,prediction=values,
            model_rank=model_rank,slam_rank=slam_rank,pose=pose,image_bgr=image)
        fig,axes=plt.subplots(1,4,figsize=(18,4))
        rgb=cv2.cvtColor(image,cv2.COLOR_BGR2RGB)
        for ax in axes:ax.imshow(rgb);ax.set_xlim(0,224);ax.set_ylim(168,0);ax.axis('off')
        axes[0].set_title(f'RGB | t={key["ts"]:.3f}')
        for x in [56,112,168]:axes[0].axvline(x,color='white',alpha=.5)
        for y in [56,112]:axes[0].axhline(y,color='white',alpha=.5)
        axes[1].scatter(*uv.T,c=model_rank,cmap='coolwarm',vmin=0,vmax=1,s=12)
        axes[1].set_title('Model nearness rank: red=near')
        scatter=axes[2].scatter(*uv.T,c=slam_rank,cmap='coolwarm',vmin=0,vmax=1,s=12)
        axes[2].set_title('SLAM nearness rank: red=near')
        axes[3].imshow(predicted,cmap='magma');axes[3].set_title('Model inverse depth: bright=near')
        fig.suptitle(f'Ordering correlation {entry["rank_correlation"]:.3f}; ranks normalized within this view; no metric depth')
        fig.tight_layout();fig.savefig(a.output/f'view_{index}.png',dpi=150);plt.close(fig)
        print(json.dumps({k:v for k,v in entry.items() if k!='cells'}),flush=True)
    (a.output/'spatial_diagnostics.json').write_text(json.dumps({'views':report,
        'note':'Image cells are fixed, not object segmentation. Nearness ranks are relative to projected samples per view. No ground truth.'},indent=2))


if __name__=='__main__':main()
