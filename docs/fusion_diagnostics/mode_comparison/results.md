# Local dense preview versus validated keyframe window

Two sequential 28-second timed saved-input runs used the same source sequence:
`data/sessions/1fbb44b27fc94a4daf7afc48883dc708/slam_input`.
Both used CPU Depth Anything V2 Small at 224x168, raw lossless transport, original
webcam calibration and strict initialization. Model weights and fusion thresholds
were unchanged. The timed harness now accepts `--initializer-profile strict`.

| Measurement | Local preview | Validated window |
|---|---:|---:|
| Processed outputs | 98 | 99 |
| Outputs with poses | 80 | 69 |
| Outputs showing dense points | 34 (34.7%) | 0 |
| First pose | 3.97 s | 6.66 s |
| First dense output | 4.45 s | None |
| Receipt-to-packet p50 / p95 | 322 / 502 ms | 306 / 587 ms |
| Exact image/SLAM pairing | All | All |

The older local-preview behavior remains functional in the current implementation:
it produced dense patches on this input. Such a patch is replaced on the next
output and is not a persistent cross-view-validated reconstruction. Its final
snapshot was sparse-only; dense display was intermittent rather than continuous.

The window requires accepted keyframe depths plus supporting views and useful
baseline. Its candidate-selection restrictions and fit failures were analyzed in
[the source-session investigation](../support_rejection_trial/results.md).
Both modes share the positive-scale alignment and training-quality checks; the
window adds temporal/keyframe selection and cross-view filtering.

## Limits of this comparison

The two runs have different online SLAM histories, initialization times and sampled
outputs because scheduling and optimization are asynchronous. This is not an
identical-state, identical-prediction regression test and cannot establish that the
entire difference is caused by cross-view rejection. Nor does it rule out selection
bugs or prove dense-map accuracy. It is one run per mode, not a controlled latency
benchmark. No physical webcam was acquired in these runs.

Conclusion: local depth-to-patch behavior was not simply removed or globally broken;
validated-window coverage remains an unresolved engineering issue. Preserve both
modes and their labels. Improve candidate selection under unchanged validation,
and use recorded identical SLAM snapshots/predictions for a stricter regression
test before attributing coverage changes to one mechanism.

Artifacts: [measurements](measurements.json), `data/mode_comparison_local`,
`data/mode_comparison_window`. Thirteen live-SLAM/keyframe-window unit tests passed.
Dashboard defaults and active camera calibration were not changed by this comparison.
