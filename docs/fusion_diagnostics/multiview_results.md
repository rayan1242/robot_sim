# Cross-view fusion checks

The room reconstruction is still not solved. This change addresses unsupported
dense accumulation, not the underlying weak SLAM geometry in failed clips.
Original recordings, maps and reports are preserved.

## What changed

`fuse_dataset.py --multiview-checks` implies training-only quality checks and then
requires each dense point to agree with supported depth in at least one other
accepted keyframe. The views must have at least a one-degree ray angle. Relative
z-depth disagreement must be at most 10%; a point observed in another view's
free space is rejected. Occluded points and unknown pixels provide no support.

Training-only acceptance also rejects weak or contradictory inverse-depth rank
correlation (<0.3). A nearly constant positive fit can otherwise have small
residuals despite reversed depth ordering in a narrow-range scene. These are
explicit engineering thresholds, not calibrated probabilities or independently
established safety limits. Baseline fusion without quality flags is unchanged.

## Existing room footage

For `1793498406555488000`, 8 accepted keyframes produced 19,041 voxelized points,
compared with 26,613 before cross-view filtering at the same 0.002 voxel size.
The retained per-view candidates total 23,773 before voxelization. Filtering
reduces coverage; fewer points are not proof of greater accuracy. The preview
still shows distortion and incomplete surfaces. This is not a room-scale map
ready for navigation.

Per-view held-out SLAM agreement remains 7.05%, because the aligned depth estimates
were unchanged. It is measured before dense cross-view filtering and is not a new
accuracy score for the final map. Both checks reuse the same SLAM/model outputs,
so they cannot detect all shared systematic errors.

The static-scene clip `1793499467724595200` still has no accepted fusion. It exits
with an explicit failure and saves rejection reasons instead of creating a map.
The dominant reasons remain lack of positive-scale sparse support and too few
visible observations. There is no evidence that a sign change or relaxed threshold
would recover correct geometry.

## Reproduce

The TUM regression run retained all 19 fitted keyframes with nonempty outputs:
89,559 dense candidates became 79,204 cross-view-supported candidates and 11,575
voxelized points (voxel size 0.02). Per-view held-out agreement was 5.15%.
This shows the policy retains benchmark geometry; it is not an independent
measurement of dense reconstruction accuracy.

These commands process saved images, without opening a webcam:

```powershell
python fuse_dataset.py --dataset data/recordings/1793498406555488000 --slam data/slam_webcam_1793498406555488000 --calibration data/calibration.npz --output data/fusion_webcam_multiview --max-keyframes 20 --voxel-size 0.002 --multiview-checks
python fuse_dataset.py --output data/fusion_fr1_multiview --max-keyframes 20 --voxel-size 0.02 --multiview-checks
```

Preview: `data/fusion_webcam_multiview/dense_map.png`. Full PLY, NPZ and per-view
counts are in the same directory. Failed-run report:
`data/fusion_webcam_static_multiview/report.json`.

37 Python tests pass. New regression cases cover contradictory depth ordering,
a supported plane versus floating/occluded surfaces, and identical viewpoints
or unknown depth providing no support.

The remaining blocker is reliable input scene geometry, including triangulation
conditioning and unverified calibration stability. This filtering does not repair
failed SLAM. Live SLAM/fusion integration and a recognizable full-room model remain
unfinished; Gazebo work does not resolve either requirement.
