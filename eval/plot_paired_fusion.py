"""Plot saved ablation clouds at identical bounds and view settings."""
import argparse
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,default=Path('data/paired_fusion/successful'))
    p.add_argument('--output',type=Path,default=Path('docs/paired_fusion/comparison.png'))
    a=p.parse_args()
    labels=['all','selected','all_multiview','selected_multiview']
    with np.load(a.input/'all.npz') as source:
        low=source['points'].min(axis=0);high=source['points'].max(axis=0)
    fig=plt.figure(figsize=(12,9))
    for i,label in enumerate(labels):
        ax=fig.add_subplot(2,2,i+1,projection='3d');path=a.input/(label+'.npz')
        if path.is_file():
            with np.load(path) as cloud:
                points=cloud['points'];rgb=cloud['rgb']
            sample=np.linspace(0,len(points)-1,min(len(points),20000),dtype=int)
            ax.scatter(*points[sample].T,c=rgb[sample]/255,s=1,alpha=.65)
            ax.set_title(f'{label}: {len(points):,} points')
        else:ax.set_title(f'{label}: no accepted cloud')
        ax.set(xlim=(low[0],high[0]),ylim=(low[1],high[1]),zlim=(low[2],high[2]),
            xlabel='X (arbitrary)',ylabel='Y',zlabel='Z')
        ax.set_box_aspect(np.maximum(high-low,.01));ax.view_init(elev=22,azim=-60)
    fig.suptitle('Offline final-pose ablation: shared bounds; coverage reduction is not accuracy proof')
    fig.tight_layout();a.output.parent.mkdir(parents=True,exist_ok=True);fig.savefig(a.output,dpi=160);plt.close(fig)


if __name__=='__main__':main()
