# Offline fusion diagnosis

Latest negative control: [window-heavy live-session investigation](rejected_live_session/results.md).

Follow-up: [cross-view fusion checks and current limitations](multiview_results.md).

Latest: [well-tracked segment audit and separate export](segment_results.md).

This investigation compares the failed static-scene recording
`1793499467724595200` with the successful TUM Freiburg 1 XYZ run. It uses saved map
databases and original images; no additional recording was requested.

## Coordinate and export checks

The diagnostic independently reads saved world-to-camera poses and undistorted
feature observations from stella's MessagePack map. It reconstructs camera-to-world
poses, compares them with the exported trajectory, and reprojects map landmarks
into their saved keyframe observations.

- Maximum exported-pose element difference: approximately 1e-9 for both runs.
- Calibration matrix difference from the camera stored in the webcam map: <5e-10.
- Keyframe-to-original-RGB timestamp mismatch: zero in sampled keyframes.
- Original-camera sparse reprojection median: 0.85 pixels for the failed clip and
  1.04 pixels for TUM (95th percentiles 2.28 and 3.71 pixels).

No pose inversion, calibration-file substitution, or timestamp association error
was found in these checks. Small reprojection error is internal consistency, not
proof that estimated scene depth or calibration is correct.

## Depth ordering and parallax

Eight evenly selected retained keyframes were inspected per run. Depth predictions
were sampled at distorted projections with the same resize convention used by fusion.

| Diagnostic | Failed static scene | Successful TUM |
|---|---:|---:|
| Spearman rank correlation: network output versus inverse SLAM depth | -0.68 to -0.14 | +0.86 to +0.96 |
| Median landmark maximum retained-view ray angle | 0.70 degrees | 12.28 degrees |
| 10th percentile maximum retained-view ray angle | 0.34 degrees | 2.22 degrees |

For context, the earlier successful room map had median maximum ray angle 4.03
degrees; the failed desk map had 1.89 degrees. These angles are computed from the
estimated map, so they are not independent measurements of real camera motion.

The failed static clip has weak estimated triangulation geometry, while its predicted
and SLAM depth orderings disagree. This supports unstable monocular scene geometry
as a leading explanation. It does not isolate the cause: model errors and changed
camera focus/calibration can still contribute. A blanket depth-output sign reversal
is not appropriate because TUM has the expected positive ordering, and another
webcam recording already supports positive-scale fusion.

Raw reports, sampled correspondences, and plots are in `static_scene/` and `tum/`.
The correspondences are diagnostic data; held-out observations were not used to
relax fusion acceptance thresholds.

## Separate initialization experiment

A strict profile raises only `Initializer.parallax_deg_threshold` from 1 to 2
degrees. Baseline configuration and output remain unchanged.

| Outcome on static-scene footage | Baseline | Strict trial |
|---|---:|---:|
| Inputs with live pose | 273/450 | 179/450 |
| Final landmarks | 313 | 43 |
| Median maximum retained-view ray angle | 0.70 degrees | 0.048 degrees |

The trial did not fix the geometry and is **not promoted to the default**. Results
are from one multithreaded run per configuration, not a statistical comparison.
The initial parallax check does not guarantee that later bundle adjustment and
tracking retain reliable scene depth.

The strict run is preserved at
`data/slam_webcam_1793499467724595200_strict/`. Existing footage and baseline maps
were not overwritten. No dense map is claimed for this recording.

## Validation and next work

All **22 tests pass**, including new independent pose/reprojection and known-baseline
ray-angle tests. The diagnostic tool is `python -m eval.diagnose_fusion --help`;
it requires `msgpack`, now included in `requirements-vo.txt`.

Further work should evaluate triangulation conditioning and calibration stability,
and test map consistency over time. Until then, failed webcam fusion should remain
an explicit limitation. The validated TUM pipeline and the earlier partial room map
remain available for backend/replay integration; live tracking reliability and
obstacle mapping have not been solved by this investigation.
