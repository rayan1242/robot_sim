"""Simulation-only local mapping from RGB depth plus a known flat-floor/camera prior."""
import math

import cv2
import numpy as np

from perception.fusion import fit_inverse_depth

CAMERA_HEIGHT=0.29
CAMERA_X=0.23
CAMERA_PITCH=0.12
RESOLUTION=0.05
WIDTH=60
HEIGHT=60


def camera_matrix(width=320,height=240):
    focal=width/(2*math.tan(math.pi/6))
    return np.array([[focal,0,(width-1)/2],[0,focal,(height-1)/2],[0,0,1]],dtype=float)


def local_grid(prediction,bgr):
    """Return a base-frame local occupancy grid, or reject an unsupported floor fit.

    This assumes the exact simulated camera pose, horizontal ground and gray floor.
    It is not applicable to arbitrary webcam footage or uneven terrain.
    """
    height,width=prediction.shape
    matrix=camera_matrix(width,height)
    v,u=np.mgrid[:height,:width]
    y=(v-matrix[1,2])/matrix[1,1]
    denominator=math.sin(CAMERA_PITCH)+math.cos(CAMERA_PITCH)*y
    brightness=bgr.mean(axis=2)
    gray=(bgr.max(axis=2).astype(float)-bgr.min(axis=2))<25
    mask=gray&(brightness>35)&(v>height*0.65)&(v<height*0.94)&(denominator>0.05)
    samples=np.flatnonzero(mask)[::12]
    if len(samples)<50:
        raise ValueError("Insufficient visible gray floor for scale validation")
    floor_z=CAMERA_HEIGHT/denominator.reshape(-1)[samples]
    values=prediction.reshape(-1)[samples]
    order=np.random.default_rng(0).permutation(len(samples))
    heldout,training=order[::4],np.delete(order,np.arange(0,len(order),4))
    fit=fit_inverse_depth(values[training],floor_z[training])
    evaluated=fit.depth(values[heldout])
    if not np.isfinite(evaluated).all():
        raise ValueError("Invalid held-out floor depths")
    error=float(np.mean(np.abs(evaluated-floor_z[heldout])/floor_z[heldout]))
    if error>0.2 or fit.inliers/fit.samples<0.7:
        raise ValueError("Known-floor depth fit failed validation")
    depth=fit.depth(prediction)
    grid=np.full((HEIGHT,WIDTH),-1,dtype=np.int8)
    # Sparse ray integration bounds work and keeps the local map small.
    for row in range(20,height-5,6):
        for column in range(8,width-8,6):
            z=float(depth[row,column])
            if not math.isfinite(z) or z<0.08 or z>3:
                continue
            optical_x=(column-matrix[0,2])/matrix[0,0]*z
            optical_y=(row-matrix[1,2])/matrix[1,1]*z
            forward=CAMERA_X+math.cos(CAMERA_PITCH)*z-math.sin(CAMERA_PITCH)*optical_y
            left=-optical_x
            up=CAMERA_HEIGHT-math.sin(CAMERA_PITCH)*z-math.cos(CAMERA_PITCH)*optical_y
            if forward<=0 or forward>=WIDTH*RESOLUTION or abs(left)>=HEIGHT*RESOLUTION/2:
                continue
            x=int(forward/RESOLUTION); ycell=int((left+HEIGHT*RESOLUTION/2)/RESOLUTION)
            if up < -0.06 or up>1.5:
                continue
            origin_x=int(CAMERA_X/RESOLUTION);origin_y=HEIGHT//2
            steps=max(abs(x-origin_x),abs(ycell-origin_y),1)
            xs=np.rint(np.linspace(origin_x,x,steps+1)).astype(int)
            ys=np.rint(np.linspace(origin_y,ycell,steps+1)).astype(int)
            # Occupied cells dominate free observations within this frame.
            free=grid[ys,xs]!=100
            grid[ys[free],xs[free]]=0
            if up>0.08:
                grid[ycell,x]=100
    return grid,{"heldout_floor_abs_rel":error,"training_floor_inliers":fit.inliers,
                 "floor_samples":len(samples),"scale_reference":"known simulation camera height and flat gray floor"}


def velocity_command(grid,reliable=True,fresh=True):
    if not reliable or not fresh or grid is None:
        return 0.,0.,"stopped_unreliable"
    center=HEIGHT//2
    front=grid[center-5:center+6,6:18]
    if np.any(front==100):
        left=np.count_nonzero(grid[center+3:center+16,6:22]==0)
        right=np.count_nonzero(grid[center-16:center-3,6:22]==0)
        return 0.,0.45 if left>=right else -0.45,"turning"
    if np.count_nonzero(front==0)<front.size*0.2:
        return 0.,0.,"stopped_unknown"
    return 0.08,0.,"forward"
