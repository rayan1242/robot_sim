# First physical-webcam strict-initialization trial

Session `9086c570212e41899113fc580f536605`, 30 seconds, DirectShow 640x480,
CPU Depth Anything V2 Small at 224x168, validated keyframe window enabled.
Saved session options confirm `strict` initialization. Map snapshot saved without
warning. Original recording and map were preserved.

| Measurement | Result |
|---|---:|
| Processed outputs | 122 |
| Outputs with poses | 66/122 (54.1%) |
| First returned pose | 11.61 seconds |
| Posed outputs after initialization | 66/66 |
| Outputs with supported dense window | 3/122 (2.5%) |
| First dense window | 29.26 seconds |
| Final dense points before combined-map voxelization | 2,321 |
| Final combined sparse/dense snapshot | 2,775 points |
| Receipt-to-packet p50 / p95 | 275 / 525 ms |
| Misses of provisional 500 ms budget | 11/122 |

The low overall pose fraction includes the long initialization period. No processed
output lost its pose after the first valid pose. There was one map epoch. This is
a partial success: the stricter live configuration produced cross-view-supported
dense geometry, but only during the final three outputs, not throughout the scan.

The two final accepted keyframes have training ordering correlations of 0.718 and
0.774, with held-out mean SLAM depth disagreement of 12.37% and 10.69%, respectively.
These are selected-view consistency measurements, not independent accuracy. The
final candidate depths retained 1,173 and 1,148 points after cross-view checks.
Earlier keyframes frequently failed the unchanged training-support requirement.

The baseline recording had no dense windows. This recording is a different camera
motion/input, so comparison cannot isolate initialization as the sole cause. A
complete room reconstruction or reliable continuous dense mapping is not established.

Next target initialization delay and availability of a second accepted geometrically
useful view earlier in the recording. Keep the current rejection thresholds. Inspect
cached keyframe selection/support before reducing model size or loosening gates.

[Saved measurements](measurements.json). Raw recording and map:
`data/sessions/9086c570212e41899113fc580f536605`.
