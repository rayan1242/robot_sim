"""Check calibration sensitivity using saved checkerboard views, without a camera."""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from perception.calibrate import detect


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--images',type=Path,default=Path('data/calibration_images_03'))
    parser.add_argument('--calibration',type=Path,default=Path('data/calibration.npz'))
    parser.add_argument('--output',type=Path,default=Path('docs/fusion_diagnostics/calibration_stability.json'))
    args=parser.parse_args()
    with np.load(args.calibration) as saved:
        board=tuple(int(v) for v in saved['board_size']);size=tuple(int(v) for v in saved['image_size'])
        square=float(saved['square_size']);reference=saved['camera_matrix']
    template=np.zeros((board[0]*board[1],3),np.float32)
    template[:,:2]=np.mgrid[0:board[0],0:board[1]].T.reshape(-1,2)*square
    views=[]
    for path in sorted(args.images.glob('*.png')):
        image=cv2.imread(str(path))
        if image is None or (image.shape[1],image.shape[0])!=size:raise ValueError('Invalid image dimensions')
        corners=detect(image,board)
        if corners is not None:views.append(corners)
    if len(views)<12:raise ValueError('Need at least 12 detected board views')
    rng=np.random.default_rng(42);order=rng.permutation(len(views));trials=[]
    for fold in range(4):
        test=order[fold::4];train=np.setdiff1d(order,test)
        rms,matrix,distortion,_,_=cv2.calibrateCamera([template]*len(train),[views[i] for i in train],size,None,None)
        errors=[]
        for i in test:
            ok,rvec,tvec=cv2.solvePnP(template,views[i],matrix,distortion)
            if not ok:raise RuntimeError('Held-out board pose could not be solved')
            projected,_=cv2.projectPoints(template,rvec,tvec,matrix,distortion)
            errors.extend(np.linalg.norm(projected-views[i],axis=2).reshape(-1).tolist())
        trials.append({'training_views':len(train),'heldout_views':len(test),'training_rms_px':rms,
            'fx':float(matrix[0,0]),'fy':float(matrix[1,1]),'cx':float(matrix[0,2]),'cy':float(matrix[1,2]),
            'heldout_reprojection_rms_px':float(np.sqrt(np.mean(np.square(errors))))})
    hull=cv2.convexHull(np.vstack(views).astype(np.float32))
    result={'views':len(views),'image_size_wh':size,'saved_fx':float(reference[0,0]),
        'corner_hull_image_fraction':float(cv2.contourArea(hull)/(size[0]*size[1])),
        'folds':trials,'fx_relative_range':float(np.ptp([t['fx'] for t in trials])/reference[0,0]),
        'note':'Sensitivity test only. Held-out board poses are fitted; low reprojection error does not establish correct intrinsics or unchanged webcam focus.'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
