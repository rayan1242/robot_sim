# Stricter initialization on the same saved webcam input

Fresh baseline and strict offline SLAM runs each consumed the same 449 archived
RGB frames/timestamps from session `818d5311fda343eab93f617e25ea9b71`.
Original session data, calibration and maps were preserved. Both use the same
webcam calibration and ORB settings; the strict YAML changes initializer minimum
parallax from the upstream default 1 degree to 2 degrees. Depth predictions,
fusion gates and model weights were not changed.

| Result | Baseline rerun | Strict rerun |
|---|---:|---:|
| Inputs with a returned pose | 385/449 (85.7%) | 341/449 (75.9%) |
| First returned-pose timestamp | 4.304 s | 7.248 s |
| Final keyframes | 9 | 7 |
| Final landmarks | 734 | 551 |
| Three-view ordering correlations | -0.709, -0.772, -0.620 | +0.717, +0.739, +0.752 |

All seven strict-map keyframes were subsequently audited at 224x168: ordering
correlations are positive, from 0.580 to 0.775. Its internal reprojection residual
is 0.86 px median / 2.92 px p95, which is consistency rather than independent
accuracy. Final retained keyframes differ between runs: these ordering summaries
are not identical-correspondence or identical-frame quality comparisons.

The strict map's first spatial overlay now places the foreground bed nearer than
the rear-wall switch, consistent with the visually apparent ordering. See the
[strict first view](strict_rerun/view_0.png) versus
[baseline first view](baseline_rerun/view_0.png). They show nearby, different input
frames; no claim of exact pixel matching is made.

Fresh offline fusion on all seven strict-map keyframes, at the existing offline
320x240 setting, retained all seven and produced **3,222 voxelized dense points**
with training gates and cross-view checks enabled. Held-out mean disagreement is
**8.97% over 373 valid SLAM associations**, not independent depth accuracy.
The result is a partial surface reconstruction with holes, not a complete room.

![Strict-map dense reconstruction](../../../data/fusion_latest_strict_trial/dense_map.png)

## Interpretation and limits

This is a successful correction experiment on the previously failing recording.
It supports initialization geometry as a contributing factor without proving
calibration is correct or identifying a unique cause. Delaying initialization
also changes which frames seed the map. Mapping is multithreaded/stochastic, and
only one run per profile was performed; this does not establish a robust fix.
Tracking coverage decreased by 9.8 percentage points and startup took longer.

The baseline reproduces the original ordering contradiction. The strict result
uses stronger initial parallax without weakening depth rejection. Do not invert
the depth model or force rejected frames into the map. The existing live default
has not been changed based on this single experiment. Next validate strict
initialization through timed input and repeated recordings before adopting it.

This runner processes saved frames offline without real-time scheduling; its
behavior/timing must not be reported as a live webcam trial.

Artifacts:

- [Machine-readable comparison](initialization_comparison.json)
- [All-seven-view strict audit](strict_audit224/diagnostics.json)
- [Strict fusion report](../../../data/fusion_latest_strict_trial/report.json)
- SLAM outputs: `data/slam_latest_baseline_trial`, `data/slam_latest_strict_trial`.
