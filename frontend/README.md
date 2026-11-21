# MONO spatial dashboard

A local, buildless dashboard served by FastAPI at `/`. Open the same origin/port
as your backend, e.g. `http://127.0.0.1:8001/`. No separate frontend server or build
step is required. Restart an existing backend process once after adding these routes.

```powershell
python -m uvicorn backend.app:app --host 127.0.0.1 --port 8001
```

The dashboard provides:

- Orbit/zoom/pan inspection of a capped 5,000-point map snapshot, sampled trajectory,
  and camera frustum. Fit, reference-grid, and trajectory controls are available.
- Saved RGB previews, timestamped playback, explicit replay start/stop, and speed
  selection for the next replay. Replay restarts from the beginning after stopping.
- Session selection, download, and deletion with a confirmation dialog.
- New camera recording with an explicit `dshow` request, duration, dimensions,
  camera index, and optional cached-model relative-depth saving.
- A relative-depth overlay when saved depth arrays exist. Per-frame percentile
  coloring is for visualization and does not represent meters.
- Recorded timing plots and p50/p95 values for the latest 120 received samples.
  Missing imported timing remains unavailable, rather than being fabricated.
- Automatic WebSocket reconnect and skipped-update status.

The initial saved preview does not start camera access or replay. A validated
offline import is selected first when one exists. Use **Start replay** to animate
the camera and trajectory, or **New recording** to access the webcam.

Maps are **final static snapshots**, not growing reconstructions. Poses in replay
are saved optimized results. Live recording has no live SLAM or fusion; it reports
pose unavailable. The reference grid is not an estimated ground plane. Coordinates
remain arbitrary SLAM units. The dashboard is not the ROS/Gazebo robot simulator.

## Implementation

`app.js` owns API controls and rendering state. `protocol.js` assembles each JSON
header and its ordered binary payloads before updating the UI. It validates lengths,
point count, finite geometry, and normalized RGB values. `viewport.js` uses bounded,
preallocated Three.js buffers; static snapshots upload once per selected source.
The OpenCV-to-display rotation is shared by cloud, trajectory, and camera frustum.
Gaps with unavailable poses do not create a new trajectory segment.

WebGL failure leaves session/camera controls usable with an explicit 3D-unavailable
message. Responsive layouts cover desktop and mobile widths. Camera capture remains
on the computer running the backend; opening this UI on another device does not
redirect capture to that device.

Three.js 0.180.0 is bundled in `vendor/` from the official npm package. Its MIT
license is included as `vendor/LICENSE-three.txt`. No CDN, remote fonts, npm install,
or network image service is needed at runtime.

## Checks

```powershell
node --test tests/test_frontend_protocol.js
python -m unittest discover -s tests
```

Browser QA is in `tests/browser_dashboard.py`. It uses installed Chrome, a project-local
Playwright installation at `.cache/browser-qa/`, and an isolated backend on port 8002
with session root `.cache/dashboard-qa/sessions`. Prepare a TUM import in that root
and run that test server before the script. Synthetic timing/depth fixtures exist
only inside that test session directory and are deleted by the browser test.
