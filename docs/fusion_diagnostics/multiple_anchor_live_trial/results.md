# Multiple-anchor live trial: dense points appeared, then disappeared

Session `a934304385684437bed057244f50eee1`; 105 outputs, 81 with poses.
Every state confirms `all_cached` selection. Strict initialization and the same
224x168 depth input were active. First current pose appeared at 4.83 seconds.

Dense mapping occurred on 25/105 outputs, first at 15.30 s and last at 28.72 s,
with a peak of 4,033 supported dense points. This span does not imply uninterrupted
dense output. The last dense output contained 2,507 dense points, using views
[12,21,22,23]. At 28.93 s the selected set changed to [16,22,23,24], with zero
supported dense points; subsequent outputs remained sparse-only.

Final per-view fits were accepted for views 12,16,22,23,24. The window implementation
keeps the newest four accepted views, so view 12 was still cached/accepted but
excluded from cross-view checks. All points in the final selected four were marked
unsupported, with no observed free-space conflicts. This does not uniquely
distinguish insufficient ray angle, missing overlap, occlusion or depth disagreement.
The transition also involves updated poses/geometry; these logs alone cannot
attribute the entire loss to dropping view 12.

This is a window-composition problem to investigate, not failure of depth inference
or absence of dense output throughout the recording. Multiple-anchor exploration
worked live but did not ensure persistent useful view diversity.

Next replay identical snapshots to compare newest-four window selection with a
bounded window retaining geometrically useful accepted anchor views. Keep depth
and cross-view thresholds, current-pose rebuilding, cache and inference limits.
Do not retain an old world-space cloud after its geometry fails validation.

Receipt-to-packet median was 283 ms, p95 663 ms, with 19/105 misses of 500 ms.
Additional view inference has a compute cost; this single moving-camera trial does
not isolate timing effects. No independent map accuracy was measured.

[Measurements and final rejection details](measurements.json).
