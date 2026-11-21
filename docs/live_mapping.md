# Experimental live SLAM and local dense preview

An additional **opt-in validated keyframe window** is now available. See its
[behavior, latency cost and validation](active_keyframe_window/results.md).
The default local-preview behavior described below remains available.

The dashboard can now run webcam capture, persistent WSL stella SLAM, depth and
local fusion during acquisition. This is an experimental live mapping mode,
not a validated full-room reconstruction system.

## Run it

The live runner has been built locally. Restart the existing backend to load the
new request field and worker, then hard-refresh the dashboard:

```powershell
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8001
```

Open `http://127.0.0.1:8001/`, choose **New recording**, keep capture at **640x480**,
and enable **Live SLAM and map (experimental)**. This automatically enables depth.
Begin with 320x240 depth input for geometric detail. Smaller depth inputs are
available, but earlier experiments showed reduced fit coverage. DirectShow and
auto exposure are requested by the dashboard.

Move slowly sideways while viewing stationary textured objects at different
distances. A stationary camera or turning in place may never initialize a usable
monocular map. Camera pose and points appear only after successful initialization.
The source note explains when the dense preview is withheld. Initialization,
tracking and fusion may fail; no measurements or points are fabricated.

## What the map means

- Gray points: current global sparse SLAM snapshot, updated as SLAM maps the scene.
- Colored points: the current frame's dense depth aligned to observed SLAM landmarks.
- The dense patch is **replaced**, not accumulated across all historical frames.
- Units remain arbitrary. No metric obstacle distances or navigation capability.
- Display transmission is capped at 5,000 points; SLAM snapshots contain at most
  10,000 retained landmarks before adding the local dense patch.

Replacing the dense patch prevents old patches accumulating under outdated poses.
It does not implement full correction-aware dense reconstruction. Sparse snapshots
come from an asynchronously optimized SLAM map; they are not atomic, independently
validated geometry. Online pose history is not retroactively optimized in the browser.
Map-reset epochs clear the displayed trail, and empty maps clear old points.

Training support/rank/hull checks gate local dense fusion; held-out SLAM agreement
is reported without relaxing the thresholds. It remains agreement with an estimated
map, not independent depth accuracy. Sparse mapping can continue when dense fusion
is rejected. Tracking loss never reuses a previous pose for a new dense prediction.

## Data flow and timestamps

The existing latest-frame capture thread supplies an independent SLAM consumer.
The persistent C++ process reads each selected raw image and its capture-relative
timestamp over a request/response protocol. Requests have one outstanding response;
the output reader and latest-result slot are bounded. The depth worker takes the
latest completed SLAM frame, retaining that exact image and frozen response during
inference. Sequence and timestamp mismatches are rejected. A slow depth worker does
not block capture or require SLAM to wait for each inference.

The default transport sends lossless raw BGR frames over a length-prefixed pipe.
PNG source frames are archived under `slam_input/rgb/` after reply publication.
The earlier shared-PNG route remains available to the benchmark harness; this is
not a zero-copy implementation. See the [successful-session follow-up](successful_live_session/next_steps.md)
for transport and depth-resolution comparisons. `rgb.txt`, runner logs, optimized
SLAM trajectories and a final MessagePack map are saved under `slam_input/`.
The main session stores processed RGB/depth states and the final displayed map.
Replay shows that final snapshot, not incremental historical map updates, and
labels its recorded online poses separately from offline optimized poses.

Capture must match the 640x480 calibration. The bridge checks the saved calibration
against the SLAM profile before launch and rejects mismatches. Time association
uses timestamps passed from the same source frame; no subtraction of independent
WSL/Windows absolute clocks is used. Timing still excludes hidden sensor buffering
and physical display latency.

## Verification

48 Python tests and four JS protocol tests pass. Synthetic geometry tests cover
local point generation, depth rejection and tracking loss. Browser tests check
same-session changing point counts, clearing a reset map, camera/pose rendering,
session controls and existing offline replay. Synthetic UI samples are not included
as measurement data.

The persistent runner processed a saved 300-frame clip and emitted tracked poses
and sparse-map snapshots. This is a protocol test, not a new accuracy benchmark.

A complete worker test used the earlier room recording as timed input to a
latest-frame capture slot, with real SLAM and depth inference. After stopping the
out-of-scope Gazebo processes, the 22-second run produced:

- 40 processed outputs; 24 with online poses.
- 18 accepted local dense previews.
- 2,371 points in the final snapshot.
- Exact capture/SLAM sequence and timestamp pairing on every processed output.
- 148 frames delivered to SLAM; other input frames were skipped rather than queued.

The earlier run with the old simulator still active had only 2 posed outputs and
ended with an empty map after reset. This is a single-run comparison under
uncontrolled scheduling and background load, not proof of causality or a
repeatable speed/accuracy gain. Both attempts are preserved.

An eight-second actual-webcam/API/browser check produced 18 RGB/depth outputs
through the SLAM transport with correct sequence/time matching and no page errors.
It did not initialize a pose; no deliberate camera motion was supplied. Actual
moving-camera reconstruction remains to be evaluated by the user. The observed
receipt-to-packet p95 was 707 ms; the short run does not establish a reliable tail
latency estimate or meet the provisional 500 ms budget.

Raw artifacts: `data/live_slam_protocol_smoke/`, `data/timed_live_pipeline/`,
`data/timed_live_pipeline_no_sim/`, and the hardware check in the isolated QA store.
The user session library and earlier best maps were not replaced.

Rebuild if needed:

```powershell
wsl -d Ubuntu -- bash /mnt/c/Users/Rayyan/developer/robot_sim/slam/build_live_wsl.sh
```

`python -m eval.live_slam_smoke` tests the persistent protocol with saved RGB.
`python -m eval.timed_live_pipeline --output data/live_pipeline_check_02` exercises
the asynchronous worker without accessing a physical camera; choose a fresh output
directory. These tools use existing recordings and cached model weights.
