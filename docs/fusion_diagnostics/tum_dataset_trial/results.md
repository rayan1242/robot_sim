# TUM dataset trial after the latest webcam rejection

Input: locally available TUM Freiburg 1 `xyz`, 798 timestamped RGB images.
Fresh depth inference and conservative fusion were run against the existing saved
`data/slam_fr1_xyz` optimized map. SLAM was not rerun. No webcam calibration or
reference trajectory was supplied to depth/fusion. Existing outputs were preserved.

## Results

| Measurement | Result |
|---|---:|
| 224x168 ordering audit | 8/8 sampled views positive |
| Inverse-depth Spearman range | 0.721–0.938 |
| 320x240 fusion | 19/19 keyframes retained |
| Held-out SLAM relative depth disagreement | 5.15% mean; 2.98% median |
| Held-out valid associations | 1,456 |
| Cross-view-supported points before voxelization | 79,204 |
| Final voxelized points | 11,575 |
| Saved trajectory, Sim(3)-aligned ATE RMSE | 0.01058 m (795 associations) |

The independent reference is a camera trajectory, not depth ground truth. Alignment
uses the reference to resolve scale/rotation/translation for evaluation; it does not
make the deployed map metric. Depth disagreement measures agreement with estimated
SLAM, not real-world dense-map accuracy. The audit and fusion run use different
input resolutions as explicitly listed above; this is not a resolution comparison.

Strict training support, positive inverse-depth scale, rank correlation, image
support, cross-view ray angle, depth consistency and free-space rejection remain
enabled. Final map units are arbitrary. The resulting map shows supported tabletop
surfaces with holes and incomplete coverage, not a complete room reconstruction.

## Interpretation

Unlike the latest webcam clip, the sampled dataset views agree in near/far ordering.
The model and fusion implementation can produce a supported reconstruction on this
benchmark. This does not isolate the webcam failure or establish robustness across
scenarios: input scene, motion, calibration and final geometry differ. It is also
an offline final-map test, not a live active-keyframe-window performance test.

The dataset was imported as **TUM dataset - strict fusion trial**, with 100
sampled RGB/depth frames and the final static map for dashboard replay. Refresh
the session library to select it. Playback speed is not inference speed.
Session ID: `db9330d7704942c58083780b61005df6`; all 100 sampled frames have saved poses.

## Evidence

- [224-input diagnostics](audit224/diagnostics.json)
- [Ordering scatter plots](audit224/correspondences.png)
- [Trajectory evaluation](trajectory_evaluation.json)
- [Fusion report](../../../data/fusion_tum_dataset_trial/report.json)
- [Map preview](../../../data/fusion_tum_dataset_trial/dense_map.png)

Next: localize the webcam ordering failure with recognizable object correspondences.
The TUM success supports keeping the current model as a control before replacement.

Follow-up: [TUM through the live worker](../tum_live_path_trial/results.md) now
tests the live scheduling and active-keyframe window with dataset calibration.
