# Brighter desk recording: 1793510972945292300

All 300 frames at 640x480 were processed using the existing webcam calibration,
the unchanged baseline stella profile and conservative cross-view fusion.
Previous recordings, maps and the dashboard's best replay were preserved.

## Measurements

| Measurement | New recording |
|---|---:|
| Recorded duration | 20.00 s |
| Median per-frame grayscale median | 50.5/255 |
| Median fraction of pixels below 30/255 | 46.5% |
| Available live poses | 136/300 (45.3%) |
| Saved optimized frame poses | 137 |
| Final keyframes / landmarks | 7 / 178 |
| Landmark observation links | 739 |
| Median maximum retained-view landmark ray angle | 2.79° |
| Sparse reprojection median / p95 | 0.64 / 2.00 px |
| Depth versus inverse-SLAM-depth rank correlation across sampled views | +0.57 to +0.68 |
| Fused views / total views | 2 / 7 |
| Final voxelized points | 4,083 |
| Accepted-view held-out samples | 38 |
| Accepted-view held-out relative error mean / median | 21.49% / 6.23% |

SLAM initialized from input frames 160 and 164, about 10.7–11.0 seconds into the
recording. The 136 available live poses cover frames 164–299. Most unavailable
frames are therefore startup, not tracking failures after successful initialization.
The optimized export also retains the initialization reference frame, explaining
the different counts. Availability is not accuracy.

The new clip is brighter than the previous one (median 1/255), and the driver was
asked for automatic exposure. Driver readback remains unsupported (-1), so setting
acceptance alone is not proof of hardware state. This was not an isolated exposure
experiment: scene and motion also differ between recordings.

## Interpretation

Initialization now succeeds and the depth ordering agrees moderately with sparse
SLAM depths. Five views still fail the existing training-support checks. The two
accepted views have held-out mean errors of 25.29% and 16.27%; their pooled mean is
21.49%. These held-out samples are not used to tune or relax acceptance.

The final map is a small incomplete surface patch, not a reliable desk or room
reconstruction. Cross-view filtering does not turn its per-view agreement into
independent accuracy. Low reprojection error is internal consistency, not evidence
that sparse scene depths are physically correct. The ray-angle distribution also
has a weak tail (10th percentile 0.093°).

This improves on the previous clip's complete initialization failure, but it does
not outperform the earlier best room segment (4.49% held-out agreement). Scenes,
coverage and support differ, so these are diagnostic comparisons, not a controlled
accuracy ranking. The better existing dashboard map was not replaced.

No additional recording was requested during this processing pass. The next capture
should be planned around clearly textured, stationary objects at multiple distances
and deliberate sideways motion; the current laptop/wall scene still provides
limited useful structure. Acquisition changes cannot yet be claimed to isolate
the remaining fusion disagreement.

## Outputs

- SLAM: `data/slam_webcam_1793510972945292300/`.
- Dense map, preview and report: `data/fusion_webcam_1793510972945292300/`.
- This folder: sparse-map preview, validated export summary, sampled depth/SLAM
  correspondences, plots and `diagnostics.json`.
- Sampled RGB strip: `data/latest_scan_frames.jpg`.

These are saved-data experiments; no code changes or new test runs were needed.
