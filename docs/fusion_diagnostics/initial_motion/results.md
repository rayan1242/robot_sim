# Starting-motion comparison

Compared the recorded initialization frame pairs from the SLAM logs for the
partially successful strict live session and its failed repeat. Archive row indices
match the retained first keyframe timestamps; SLAM trigger indices are taken from
the logs. Active calibration was unchanged.

An independent OpenCV diagnostic extracted 2,000 ORB features, used Hamming matching
with a 0.75 ratio test, undistorted points, and fitted a homography (3 px RANSAC)
and essential matrix (normalized coordinates, approximately 1 px RANSAC, confidence
0.999). RNG seed was 42. Estimated rotation compensated bearing angles are reported
only on recoverPose positive-depth matches. These are not the exact SLAM matches
or hypotheses, and threshold-dependent fractions cannot select the better model.

| Diagnostic | Partial success | Failed repeat |
|---|---:|---:|
| Initialization pair source times | 0.81–11.41 s | 0.80–13.49 s |
| Ratio-test matches | 1,285 | 1,380 |
| Homography-supported matches at 3 px | 68.3% | 92.7% |
| Essential inliers at approximately 1 px | 85.7% | 91.4% |
| Positive-depth matches from independent pose recovery | 1,101 | 18 |
| Median raw pixel displacement | 35.3 px | 12.4 px |
| Median estimated rotation-compensated angle | 2.45 degrees | 1.11 degrees |

The failed repeat has many feature matches but little geometrically useful motion
in this diagnostic. Almost all matches can be explained by a homography, and
essential-pose recovery yields very few positive-depth correspondences. This is
consistent with a poorly constrained starting geometry (rotation-dominated motion,
near-planar observations, or related ambiguity). It does not prove which mechanism
occurred. Its angle estimate is especially fragile because only 18 matches remain.

This explains why more feature matches and a 2-degree SLAM initialization setting
alone cannot establish a physically correct map. Different algorithms, samples and
estimated rotations can disagree on parallax; the OpenCV angle does not certify
that SLAM ignored its configured threshold.

## Next controlled experiment

Use the current calibration and strict profile, with a deliberate lateral camera
translation at the start while keeping the same foreground and background in view.
Keep camera direction approximately fixed rather than panning to follow an object.
Include objects at different depths and avoid movement of scene objects. A specific
travel distance cannot guarantee a parallax angle because object distance matters.

Before asking for more blind recordings, instrument the actual SLAM initializer's
candidate support/ambiguity measurements and consider postponing or resetting an
initialization that is inconsistent with independent evidence. Any added rejection
policy needs validation on both benchmark and recorded webcam controls, with startup
time and initialization failures reported. Do not flip model depth signs or lower
fusion support thresholds.

These two pairs support a motion/initialization diagnosis, not a proven universal
fix. The fresh checkerboard validation did not show a large calibration mismatch.
[Numerical evidence](comparison.json).

## Actual initializer instrumentation

Added `slam/instrument_initializer.py` and
`slam/build_initializer_diagnostics_wsl.sh`. The patch operates on the local Linux
build copy only, not the cached pinned source. It logs each actual initializer pose
hypothesis's valid/triangulated point counts, parallax statistic and configured
thresholds before the existing gates. No decision expressions changed. The library
compiled and was installed into the existing local WSL prefix.

`run_live_wsl.sh` enables these logs for subsequent live workers. Logs go to the
session's `slam_input/runner.log`, not the JSON reply stream. Logging adds overhead;
do not compare timings with older runs as a controlled optimization result.
The upstream statistic is its selected sorted correspondence-angle statistic,
not a median camera-motion measurement.

A protocol/diagnostic check consumed the first 230 archived images of the failed
repeat, returning 868 candidate log rows and no pose. At the final attempt, the
strongest hypothesis had 93 valid points, 88 triangulated points and approximately
0.704 degrees parallax, below the configured 2 degrees. Another hypothesis had
4.149 degrees but only one valid point. The existing gates correctly refused
initialization in this saved-input run. It is not the same asynchronous execution
as the original physical recording and does not reproduce its initialization.

Evidence: `data/initializer_diagnostics_smoke/verification.json` and `runner.log`.
The logging is implemented and exercised; a new ambiguity rejection policy is not
implemented or validated. Rebuilding via the general source-copy build script can
replace the instrumented copy; rerun the dedicated diagnostic build to restore it.
