# Why this live recording withheld every dense preview

Session: `93601a495a6147a88e625fa1f03345c9`. Capture was 640x480 with
224x168 relative depth. Original images, sparse map and acceptance thresholds were
preserved. This investigation did not request another recording.

## Actual live outcome

134 processed outputs, 115 with an online pose, zero accepted dense previews.

| Rejection | Outputs |
|---|---:|
| Nonpositive inverse-depth scale during robust refinement | 106 |
| Weak or contradictory training depth ordering | 8 |
| No tracked pose | 19 |
| Fewer than 70 visible observed landmarks | 1 |

Sparse SLAM tracking therefore worked for most processed outputs, but it did not
provide depth correspondences compatible with dense alignment. Tracking availability
is not proof of scene-depth accuracy. The fitter starts from positive-scale RANSAC
hypotheses; unconstrained refinement can still produce a nonpositive slope, which
is explicitly rejected. Clamping it to a tiny positive number would not establish
a correct depth map.

## Coordinate, timestamp and ordering checks

The final saved map contains eight keyframes. At their exact original RGB times,
the diagnostic independently reconstructs camera-to-world poses and reprojects
landmarks against stored observations. It then evaluates the depth model at both
320x240 and the recording's actual 224x168 size.

| Check | Result |
|---|---:|
| Maximum pose-export element difference | <9e-10 |
| Camera-matrix difference from saved map | <5e-10 |
| Sampled keyframe/RGB timestamp difference | 0 |
| Sparse reprojection median / p95 | 0.94 / 2.94 px |
| Model-output versus inverse-SLAM-depth rank correlation, 320x240 | −0.44 to −0.90 |
| Same ordering test, native 224x168 | −0.37 to −0.89 |

All eight sampled views have negative ordering at both sizes: features the model
orders nearer are generally ordered farther by SLAM, or vice versa. Positive scale
and shift preserve ordering, so they cannot repair this contradiction. The tests
did not reveal a pose inversion, calibration-file substitution or frame association
error. Small reprojection error is internal map consistency, not independent depth
or calibration accuracy.

The diagnostic uses final optimized geometry and freshly recomputed depth, not the
exact transient landmark positions used by each live rejection. Full original live
correspondence snapshots were not saved. The contradiction surviving final map
optimization is additional evidence, not an exact replay of every failed fit.

## Geometry and overlap

Adjacent retained keyframes share a median 593 landmarks, but have median estimated
ray-angle change of only 0.76°. Across retained views, a landmark's maximum angle
has median 1.92° and 10th percentile 1.03°. Lots of shared matches do not guarantee
well-conditioned depth estimation.

Filtering the audit samples by fixed estimated maximum-angle thresholds did not
recover the expected ordering:

| Minimum maximum ray angle | Samples per view, range | Rank correlation across views |
|---|---:|---:|
| All | 251–792 | −0.37 to −0.89 |
| ≥1° | 179–775 | −0.57 to −0.89 |
| ≥2° | 14–487 | −0.15 to −0.81 |
| ≥3° | 0–4 | Too few samples |

These are diagnostics based on estimated SLAM geometry, not externally measured
baselines. No thresholds were selected to manufacture a passing result. A simple
angle filter is insufficient for this recording.

## What the images suggest, and what remains unknown

Sampled RGB shows bright outdoor/window content behind dark nearby objects.
Backlighting reduces visible foreground detail, while glass, reflections and
outdoor vegetation can complicate model/feature interpretation. These are plausible
contributors, not isolated causes. Calibration matching does not establish that
the webcam's physical focus remained unchanged.

The evidence supports an incompatible model/SLAM depth ordering, with limited
triangulation leverage. It does not establish which estimator is correct. A blanket
model sign reversal is unjustified: other recordings and the TUM benchmark already
show positive ordering with this same model and projection convention.

The correct behavior remains **sparse map only** for this clip. Faster inference
does not resolve geometry: its measured p95 software receipt-to-packet age was
344 ms with zero misses of the provisional 500 ms deadline, yet dense fusion still
failed. This is one short observation, not a timing reliability guarantee.

## Next engineering experiment

Use the successful session as a positive control and this one as a negative control.
Evaluate keyframe selection and multi-view consistency on both; include rejection
coverage and do not force every input into a dense map. A foreground/window masking
ablation on saved frames could test whether background features dominate, but is
not yet implemented. Independent depth references are needed to distinguish learned
depth error from triangulation error decisively. A smaller model or relaxed fit
threshold would not, by itself, solve the observed ordering reversal.

Raw artifacts: [320-size audit](diagnostics.json),
[native-size audit](native224/diagnostics.json),
[native correspondences](native224/correspondences.png),
[overlap](overlap.json), [geometric subsets](geometric_subsets.json).
53 Python tests pass after extending the diagnostics to explicit inference sizes
and preserving landmark IDs in the correspondence archive.
