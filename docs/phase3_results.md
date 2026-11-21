# Phase 3: mini visual odometry baseline

Original TUM Freiburg 1 XYZ sequence, RGB-only, 798 frames, stride 1.
No depth, IMU, or ground-truth motion is used during estimation.

| Measurement | Result |
|---|---:|
| Associated output poses | 796 |
| Accepted motion steps | 518 / 797 (65.0%) |
| Lost steps | 262 |
| Low-motion steps | 17 |
| Sim(3)-aligned positional ATE RMSE | 0.1677 m |
| Median position error | 0.1315 m |
| p95 position error | 0.2872 m |
| Mean VO processing time, excluding image loading | 72.3 ms |

Artifacts: `data/vo_fr1_xyz/report.json`, `tracking.csv`, `trajectory.txt`, and
`trajectory.png`. Generated data and outputs are gitignored; rerun `python vo_dataset.py`
to reproduce the pipeline. Exact feature matching and RANSAC results can vary across
OpenCV versions and hardware.

The plot shows a visibly compressed, drifting estimate relative to ground truth.
This is a weak baseline, not evidence of reliable localization. A single global scale
alignment does not correct the unit-step assumption, wrong translation directions,
or lost steps. Held poses on tracking failures remain in the error calculation.
The acceptance rate is not an independent measure of motion accuracy.

All 11 automated tests passed, including synthetic relative-motion recovery, pose
transform convention, blank-frame handling, timestamp association, and similarity
alignment. Real-data evaluation used the built-in positional evaluator; `evo` has
not been independently run.

Next: compare a production SLAM system on the identical full RGB sequence. Webcam
calibration remains pending. This baseline does not provide a sparse map or consistent
relative translation scale for fusion.

Dataset and calibration sources:
[TUM dataset](https://cvg.cit.tum.de/data/datasets/rgbd-dataset/download),
[TUM calibration and pose formats](https://cvg.cit.tum.de/data/datasets/rgbd-dataset/file_formats).
