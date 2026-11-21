"""Prepare an isolated, geometry-preserving CLAHE trial for a dark recording."""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise ValueError('Use a fresh trial output directory')
    rows=[s.split() for s in (args.dataset/'rgb.txt').read_text().splitlines() if s.strip() and not s.startswith('#')]
    args.output.mkdir(parents=True)
    clahe=cv2.createCLAHE(clipLimit=2.0,tileGridSize=(8,8));orb=cv2.ORB_create(nfeatures=2000)
    before=[];after=[];levels=[];dark=[];index=[]
    for i,(timestamp,name) in enumerate(rows):
        path=(args.dataset/name).resolve()
        if not path.is_relative_to(args.dataset.resolve()):raise ValueError('Invalid RGB path')
        image=cv2.imread(str(path))
        if image is None:raise ValueError('Missing image')
        lab=cv2.cvtColor(image,cv2.COLOR_BGR2LAB);lab[:,:,0]=clahe.apply(lab[:,:,0])
        enhanced=cv2.cvtColor(lab,cv2.COLOR_LAB2BGR)
        gray=cv2.cvtColor(image,cv2.COLOR_BGR2GRAY)
        levels.append(float(np.median(gray)));dark.append(float((gray<30).mean()))
        before.append(len(orb.detect(gray,None)));after.append(len(orb.detect(cv2.cvtColor(enhanced,cv2.COLOR_BGR2GRAY),None)))
        destination=args.output/'rgb'/f'{i:06d}.png';destination.parent.mkdir(exist_ok=True)
        if not cv2.imwrite(str(destination),enhanced):raise RuntimeError('Image write failed')
        index.append(f'{timestamp} rgb/{i:06d}.png')
    (args.output/'rgb.txt').write_text('\n'.join(index)+'\n')
    result={'original_dataset':str(args.dataset),'frames':len(rows),'median_frame_gray_level':float(np.median(levels)),
        'median_fraction_pixels_below_30':float(np.median(dark)),
        'median_orb_features_before':float(np.median(before)),'median_orb_features_after':float(np.median(after)),
        'transformation':'LAB luminance CLAHE, clipLimit=2, tileGridSize=8x8; timestamps and geometry unchanged',
        'note':'Experimental preprocessing, not restored image detail; no original files changed'}
    (args.output/'trial.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
