# Phase 6: local session backend

Opt-in `keyframe_map: true` also enables SLAM/depth and uses a bounded, cross-view
validated keyframe window. See [window results and limitations](../docs/active_keyframe_window/results.md).
It is available in New recording and remains off by default because of added work.

Experimental live poses and map updates are now available with `slam: true` in
`POST /sessions/start`, or the dashboard's **Live SLAM and map** checkbox. It enables
depth and requires calibrated 640x480 capture plus the installed WSL runner.
See [live mapping behavior and limitations](../docs/live_mapping.md): the map is a
global sparse snapshot plus the current local dense patch, not accumulated dense
room reconstruction. The default remains RGB/depth-only when SLAM is unchecked.

Live freshness instrumentation and measured results are documented in
[docs/latency/results.md](../docs/latency/results.md). New capture options include
`auto_exposure` (default true), `depth_width`/`depth_height` (default 320x240), and
`deadline_ms` (default 500, an experimental budget). Live sessions persist
`timing_summary.json`. These metrics do not represent sensor-to-display latency.

FastAPI provides session controls and a shared live/replay WebSocket protocol.
Camera acquisition or replay runs in a separate spawned process. A single-slot IPC
queue and one latest-state snapshot prevent a slow subscriber accumulating a backlog.
Each slow subscriber skips updates independently; a stalled send times out after five
seconds. This backend supports one active recording or replay at a time.

## Start the server

From the repository root:

```powershell
python -m pip install -r requirements-backend.txt
Copy-Item .env.example .env
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --env-file .env
```

Use a **single Uvicorn worker**. Runtime ownership is local to that worker. Browse
`http://127.0.0.1:8000/` for the dashboard, or `/docs` for the interactive API;
`/health` reports stream state. The same paths work on port 8001 when that is your
chosen port. Restart an old server once to load the new dashboard routes.
The server is intended for local use on loopback. Set `ROBOT_SESSION_ROOT` to change
the default `data/sessions/` storage directory. Session IDs are generated UUID hex
strings, not filesystem paths.

## Import the validated offline pipeline

For an offline room replay with saved depth and measured diagnostics:

```powershell
python -m backend.import_session --dataset data/recordings/1793498406555488000 --trajectory data/slam_webcam_1793498406555488000/frame_trajectory.txt --cloud data/fusion_webcam_multiview/dense_map.npz --tracking data/slam_webcam_1793498406555488000/tracking.csv --fusion-report data/fusion_webcam_multiview/report.json --with-depth --stride 3 --name "Room reconstruction - experimental replay"
```

This session has already been prepared locally; rerunning creates another session.
`--with-depth` performs CPU inference before replay and saves matching depth arrays.
Measurements are offline processing times, not live capture latency. The dashboard
shows copied tracking/fusion reports from `GET /sessions/{id}/analysis`, or explicit
unavailable states for older sessions. See [current results](../docs/webcam_replay_results.md).

```powershell
python -m backend.import_session
```

This copies every third TUM RGB frame, the optimized SLAM trajectory, and the final
fused map into a self-contained session and prints its ID. No ground-truth poses are
used. Use `--stride 1` for all images; `--max-frames` can limit a trial. Sources remain
unchanged. For another recording, pass its `--dataset`, `--trajectory`, and `--cloud`
explicitly; default pose/map arguments belong to TUM and must not be mixed with webcam
images. The Python importer can also import RGB without a trajectory or cloud.

Imported pose timestamps are matched within 20 ms. Unmatched frames have a null pose.
The imported map is **one final static snapshot**, not a reconstruction that grows
over time. Imported timing values are null because original per-stage measurements
are unavailable. Session metadata and every state carry relevant limitations.

## Replay

In another PowerShell terminal:

```powershell
$sessions = Invoke-RestMethod http://127.0.0.1:8000/sessions
$replayId = ($sessions | Where-Object { $_.metadata.source -eq 'offline_import' } | Select-Object -First 1).id
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/sessions/$replayId/replay" -ContentType 'application/json' -Body '{"speed":1}'
python -m backend.client --frames 10
```

Replay uses the original frame intervals (with configurable speed), sends through
`/ws/live`, and stops at the end. The process continues independently if a client
disconnects. Restart replay with the same request. Stop it early with:

```powershell
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/sessions/$replayId/stop"
```

## Record through the API

```powershell
$recordBody = @{ name='Webcam session'; backend='dshow'; width=640; height=480; fps=15; duration=30; depth=$false } | ConvertTo-Json
$recording = Invoke-RestMethod -Method Post http://127.0.0.1:8000/sessions/start -ContentType 'application/json' -Body $recordBody
python -m backend.client --frames 10
```

The duration limit stops recording automatically. To stop sooner:

```powershell
Invoke-RestMethod -Method Post "http://127.0.0.1:8000/sessions/$($recording.id)/stop"
```

The DirectShow backend is explicit in the request and is also the API default.
Recording writes original RGB PNGs, an MJPEG `raw.avi`, per-frame monotonic timestamps,
and `states.jsonl`. The AVI uses configured FPS; **timestamps.csv is authoritative**
for real timing. Original images are retained for geometric processing.

Set `depth=$true` to run the cached depth model in the worker and save `depth_*.npy`.
Install `requirements-depth.txt` first. The API uses local cached weights only;
download the model using the existing depth setup before requesting it. A model error
marks the session as failed. Relative depth arrays are saved but are not streamed
as a separate WebSocket image in this version.

Live capture/depth currently has **no live SLAM/fusion**: pose stays null and no cloud
is invented. Depth is non-metric. Optional model latency and software receipt-to-state
age are reported; sensor/driver buffering is not included. The camera is released on
normal completion. If a driver blocks shutdown, the worker is terminated and the
session is marked error, rather than reporting a clean completion.

## API routes

| Route | Purpose |
|---|---|
| `GET /health` | Current stream state |
| `GET /sessions` | List SQLite session metadata |
| `GET /sessions/{id}` | Inspect a session |
| `POST /sessions/start` | Start a camera recording |
| `POST /sessions/{id}/stop` | Stop active recording/replay |
| `POST /sessions/{id}/replay` | Start saved-state replay |
| `GET /sessions/{id}/download` | Download self-contained ZIP |
| `DELETE /sessions/{id}` | Delete an inactive owned session |
| `WS /ws/live` | Latest live or replay state |

Concurrent starts return 409. Download and delete require an inactive session.
Restarting the server marks previously active database rows interrupted. Failed
sessions retain diagnostic files and may contain incomplete recordings.

## Wire protocol v1

One update consists of these ordered WebSocket messages:

1. JSON header, including `protocol_version`, `stream_revision`, `session_id`,
   `mode`, `state`, `sequence`, timestamp, pose, latency, payload byte lengths, and
   `subscriber_skipped_updates`.
2. If `rgb_bytes > 0`: JPEG binary message of exactly that length.
3. If `cloud_bytes > 0`: little-endian float32 binary message with N rows of
   `(x, y, z, red, green, blue)`, RGB normalized to 0..1. At most 5,000 points.

Pose order is `(tx, ty, tz, qx, qy, qz, qw)`, camera-to-world. Coordinates are arbitrary
monocular SLAM units unless independently established otherwise. `cloud_semantics`
is `final_static_snapshot` for imported maps. Both source modes use the same envelope;
clients can inspect `mode` and limitations to identify what the source actually provides.
`completed` can include the last frame payload; `error` may contain no image. Idle and
starting states also have the same envelope with zero payload lengths. Revisions
count source/status updates, so skipped updates are not strictly skipped camera frames.

## Verification

```powershell
python -m unittest discover -s tests -p test_backend.py -v
```

Tests cover process-based WebSocket replay, binary payload lengths, stop/conflict
handling, persistence of failures, bounded latest-state dropping, self-contained ZIP
downloads, safe deletion, input path rejection, and simulated camera/depth recording.
API implementation/testing follows the [FastAPI documentation](https://fastapi.tiangolo.com/advanced/testing-websockets/).
# Strict SLAM initialization trial

For the experimental 2-degree initialization profile, start the server with:

```powershell
$env:ROBOT_SLAM_INITIALIZATION='strict'
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8001
```

`/health` reports `slam_initialization_profile`. Each SLAM session saves the
selected profile and YAML path in its options. The default without this environment
variable is `baseline`. Restart with `ROBOT_SLAM_INITIALIZATION=baseline` to revert.
This profile delays initialization and can reduce pose coverage; it remains an
experimental setting. For the live trial, select 640x480, depth input 224x168,
DirectShow, and the validated keyframe window in New recording.
