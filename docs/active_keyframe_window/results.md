# Opt-in live active keyframe window

An experimental live mode now rebuilds a bounded dense window from the current
SLAM keyframe poses and landmark depths. The earlier local-preview mode remains
the default. This is not a full-room dense map or independently validated accuracy.

## Use

Hard-refresh the updated dashboard, choose **New recording**, keep capture at
640x480 and choose **224x168 depth**. Enable **Validated keyframe window
(experimental)**; this also enables SLAM and depth. The source note reports
whether a validated window exists. The map badge becomes **LIVE WINDOW** when
cross-view-supported dense points are available.

Until at least two accepted views have useful parallax and compatible depths,
only sparse points are shown. A rejected alignment is not forced into the window.
Capture in a well-lit, stationary, textured scene with slow sideways motion.
The negative window/tree recording remains a useful failure example.

## Bounded data and work

- SLAM optionally exports the newest 12 retained keyframe IDs, timestamps,
  camera-to-world poses and their landmark IDs, plus a bounded landmark snapshot.
- RGB is looked up at the exact archived keyframe timestamp; no nearest-frame
  substitution. An unarchived image is deferred until available.
- At most one new keyframe image/depth inference per processed output.
- Predictions are cached for at most eight selected keyframes. Selection uses the
  prior paired-test policy: >=70 shared landmarks, >=1-degree median ray-angle
  change and Laplacian variance >=50 at 320x240. These are engineering heuristics.
- At most four accepted keyframes contribute dense points. Pixels require another
  supporting view within 10% depth disagreement with >=1-degree ray change;
  free-space contradictions reject them. Occlusion is not positive support.
- Cached depth fits and camera-local points are invalidated when their keyframe
  pose or observed landmark coordinates change. Unchanged geometry reuses cached
  results. Changed geometry is refitted before reprojecting into the world.
- Culled/out-of-window keyframes are removed; map resets clear caches. Evicted old
  candidates are not repeatedly re-inferred. The recent archive index is bounded
  at 512 entries, and image-quality rejections at 64 entries.

This addresses old-pose/old-scale accumulation in the bounded window. It is not a
global TSDF/mesh, and the active map does not preserve every historical surface.
SLAM's exported metadata is read from an asynchronously optimized map, not an
atomic global bundle-adjustment transaction. The quality checks are not a safety
guarantee or independent accuracy test.

During current-camera tracking loss, no new keyframe prediction is admitted.
Existing validated keyframe geometry can remain visible under its updated poses;
the current-camera frustum is hidden. A complete reset clears old geometry.

The recording/replay path still stores a final displayed map snapshot; replay does
not animate historical window rebuilding. Online poses remain labeled online.

## Timed saved-input tests

Both cases used raw BGR transport, 224x168 depth, the real WSL runner, and the real
asynchronous worker. No new physical-webcam recording was requested.

| Result | Successful saved scan | Rejected saved scan |
|---|---:|---:|
| Processed outputs | 59 | 69 |
| Outputs with camera pose | 53 | 62 |
| Outputs with validated window | 37 | 0 |
| Final points, including sparse | 5,041 | 184 |
| Capture/SLAM frame-time pairing | Exact | Exact |

The negative control's 184 final points are sparse, not a falsely accepted dense
window. No fusion thresholds were relaxed. These are known recordings with newly
estimated online geometry; asynchronous SLAM histories and processed-frame subsets
can differ from previous runs. They do not measure independent accuracy.

The positive test observed at most eight cached predictions and four contributing
keyframes. Its software receipt-to-packet p50 was 384 ms, p95 **745 ms**, with
20/59 misses of the provisional 500 ms budget. A previous local-preview timed run
observed p95 481 ms, but scheduling/model histories were not controlled. The new
mode has additional inference/validation work; it is **opt-in**, not a claimed
latency improvement. Short-run p99 estimates are not reliable.

Raw [positive verification](positive_verification.json),
[positive timing](positive_timing.json),
[negative verification](negative_verification.json),
[negative timing](negative_timing.json).

## Validation and limits

61 Python tests and four JS protocol tests pass. New tests verify:

- One view alone cannot establish cross-view dense support.
- A known pose translation moves the rebuilt cloud once, without old-position ghosts.
- A global scale correction refits camera-local depth without retaining the old scale.
- Cache bounds, culling, map-reset clearing and prevention of repeated old evictions.
- Contradictory depth does not enter the dense window.
- Tracking loss retains only existing geometry and admits no new image inference.
- The API enables required stages and browser requests carry the new flag.

Browser checks cover the LIVE WINDOW badge and source note, point replacement,
map reset, existing replay controls and responsive layout. Synthetic UI samples
are not measurement data. A moving physical-webcam run of this mode remains to be
evaluated by the user; the timed tests do not establish real-scene generalization.

Build/reproduce with the existing installed SLAM dependencies:

```powershell
wsl -d Ubuntu -- bash /mnt/c/Users/Rayyan/developer/robot_sim/slam/build_live_wsl.sh
python -m eval.timed_live_pipeline --dataset data/sessions/79c2df1975674ee6bfce9c3f2bad374f/slam_input --duration 20 --depth-width 224 --keyframe-map --output data/active_window_trial_02
```

Choose a fresh output directory. These commands process saved files, not a physical
webcam. Original sessions and previous maps remain unchanged.
