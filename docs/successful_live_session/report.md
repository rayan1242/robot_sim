# Successful physical-webcam live session

Session: `79c2df1975674ee6bfce9c3f2bad374f`. Source measurements and metadata are preserved in
[measurements.json](measurements.json). The source recording is unchanged.

## Outcome

- 129 processed outputs; 122 had online poses (94.6% of outputs).
- 66 outputs included an accepted local dense preview (51.2%).
- 1308 points in the final map, which was sparse-only.
- Exact capture/SLAM frame and timestamp pairing: True.
- The full historical dense map was not accumulated or saved.

The final-frame warning does not mean dense fusion never worked. Earlier frames
passed the checks. Rejection counts and accepted-view disagreement are in the JSON.
Acceptance is not proof of accuracy; depth agreement is against estimated SLAM.

## Recorded timing

| Stage | Samples | p50 (ms) | p95 (ms) |
|---|---:|---:|---:|
| capture_to_state | 129 | 487.05 | 580.96 |
| fusion_ms | 129 | 61.70 | 85.80 |
| inference_ms | 129 | 121.63 | 156.88 |
| input_age_ms | 129 | 254.21 | 328.19 |
| postprocess_ms | 129 | 1.13 | 1.98 |
| preprocess_ms | 129 | 2.09 | 3.24 |
| slam_ms | 129 | 23.66 | 35.19 |
| total_ms | 129 | 125.71 | 159.73 |

`input_age_ms` is age on entry to the depth worker, including SLAM handoff and
latest-result waiting. `fusion_ms` also includes snapshot saving and cloud packing.
`total_ms` is depth-model preprocessing, inference and postprocessing only.
Capture-to-state ends at JPEG/packet readiness, excluding sensor buffering,
network, browser display and state serialization. Stage medians are not additive.

## Interpretation and next work

The run establishes a working live sparse-mapping baseline and intermittent
local dense previews. It does not establish a reliable full-room reconstruction.
The saved data attributes much of frame age to stages before depth processing;
the old trace cannot isolate file transfer, result waiting and SLAM execution.

Next changes add that instrumentation and test lossless raw BGR transfer to WSL
instead of reading a shared PNG on the critical path. Both paths keep exact
timestamps, and archive original frames for audit. No quality thresholds are
relaxed. Dense rejection diagnostics are retained for both accepted and rejected
frames. The UI must distinguish sparse-only maps and stop sampling send age on
completed sessions.

Follow-up: [transport, resolution, and overlap measurements](next_steps.md).
