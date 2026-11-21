# Audit of a well-tracked room segment

The 14.0–20.1 second interval of recording `1793498406555488000` was selected
from the already accepted fusion keyframes. The 24–26 second interval provides
a comparison with high existing held-out errors. Selection favors a stronger
section: it is not an unbiased estimate of full-recording performance.

| Measurement | Selected section, 14–20.1 s | Late comparison, 24–26 s |
|---|---:|---:|
| Live pose availability | 91/91 | 30/30 |
| Existing fused keyframes | 5 | 2 |
| Shared-landmark neighboring-view pairs | 1,541 | 63 |
| Median estimated neighbor ray angle | 1.33° | 0.26° |
| Neighbor dense-depth median disagreement, range across directions | 1.97–3.66% | 2.64–2.68% |
| Samples within 10% depth agreement, range | 86.9–98.9% | 87.4–90.0% |
| Mean RGB transfer error, range, intensity units 0–255 | 4.12–7.03 | 13.38–14.08 |
| Existing held-out SLAM agreement | 4.49% pooled | 31.9% and 41.3% per view |

## Interpretation

The selected segment has consistent local depth and better color alignment, with
more shared landmarks and more viewing-angle change. It is a useful small-scene
baseline for debugging. The camera intrinsics and fit conventions need not be
globally reversed or replaced to obtain locally consistent observations.

The late segment illustrates a limitation: dense predictions can agree with one
another while disagreeing with held-out sparse geometry. Tracking availability
and depth consistency alone cannot establish correct reconstruction. Weak
triangulation is a leading explanation, but estimated ray angles do not independently
prove physical camera motion. Blur, exposure, occlusion and scene changes can
also affect RGB transfer. This audit does not isolate a single root cause.

No new fit or acceptance threshold was tuned using these results. The pairwise
audit uses saved poses and saved inverse-depth fit coefficients with fresh depth
predictions at exact keyframe RGB timestamps. Supported prediction ranges are
applied, but the original training convex-hull masks are not applied to the audit
samples. Pair errors include occlusions; they are consistency diagnostics, not
ground-truth accuracy or a safety guarantee.

## Separate map export

`data/fusion_webcam_segment/` contains a 13,524-point PLY/NPZ, preview and report
from only the five selected keyframes. This export uses the original conservative
training masks and cross-view checks. Original coefficients and held-out errors
were compared with the full run and are unchanged. Held-out agreement is 4.49%,
compared with 7.05% for the larger accepted selection; this reflects changed
coverage, not an improvement of identical estimates.

This is an incomplete patch of the scene, not a recognizable, validated full-room
scan. The original map and dashboard replay were preserved. The new map was not
silently substituted into the full-recording replay.

```powershell
python -m eval.audit_segment
python -m eval.audit_segment --start 24 --end 26 --output docs/fusion_diagnostics/late_segment
python fuse_dataset.py --dataset data/recordings/1793498406555488000 --slam data/slam_webcam_1793498406555488000 --calibration data/calibration.npz --output data/fusion_webcam_segment --max-keyframes 20 --voxel-size 0.002 --multiview-checks --start-time 14 --end-time 20.1
```

All commands read saved files and do not access a webcam. Interval selection
preserves the original random training/held-out splits. New exports leave the
baseline map unchanged.

41 Python tests pass. New synthetic tests verify depth/color agreement after a
known camera translation and expose wrong or missing target depth. They found
and fixed an empty-coordinate crash in `sample_bilinear`.

## Next experiment

Use the selected section as the regression baseline. A controlled scan with a
larger sideways baseline and stationary textured objects is needed to test whether
the weak geometry can be avoided during acquisition. A further round of filtering
cannot establish missing geometry. Metric accuracy still needs a measured
reference, and broader scene coverage is needed before claiming room reconstruction.

Raw reports and source-frame strips:
[selected section](segment/report.json), [selected images](segment/frames.jpg),
[late section](late_segment/report.json), [late images](late_segment/frames.jpg).
