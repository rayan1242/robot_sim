# Phase 6: session API and replay

Implemented a local FastAPI backend with SQLite session metadata, start/stop camera
recording, offline artifact import, process-based replay, download/delete, and a shared
JSON/binary WebSocket envelope. The perception/replay process is separate from the
server, with a bounded latest-state queue. Slow clients do not block capture or build
up a history queue. The service supports one active source and multiple subscribers.

Validation:

- All **29 tests passed** (seven new backend tests).
- A real spawned replay process streamed JSON, JPEG, and little-endian point-cloud
  bytes through the test WebSocket client and completed normally.
- Active-session conflicts, stop behavior, invalid paths, archives, and persisted
  replay failures were exercised.
- The local Uvicorn server replayed a self-contained TUM import: 266 frames, matched
  optimized poses, and a final map capped to 5,000 transmitted points.
- A real API camera recording using DirectShow saved **45 states, 45 PNG frames,
  45 decodable AVI frames, and timestamps spanning 2.94 seconds** in a three-second trial.
- Optional depth artifact recording was covered with a simulated camera/model. A real
  depth inference and its standalone live preview were validated in earlier phases;
  the new live-depth API branch was not hardware-tested with the actual model.

The TUM replay session ID is `5e336ee363a44887a3c673b9872fed43`; the camera smoke-test
session is `81e4335987c64a41ace961e81a9c9572`. Both are stored under `data/sessions/`.
IDs are local artifacts, not externally published sessions.

Scope limits are explicit in metadata and protocol:

- Live recording supports camera/optional relative depth, with pose unavailable.
  Live SLAM/fusion remains unintegrated and webcam mapping reliability is unresolved.
- Imported replay uses final optimized poses and a **static final map**, not live or
  incremental reconstruction. It does not manufacture missing per-stage timings.
- Metric scale, ground plane, and occupancy mapping remain pending.
- RGB video has fixed configured playback FPS; monotonic timestamp files retain
  actual spacing. Server timestamps for latency omit hidden sensor/driver buffering.
- The service is a single-worker local backend, without deployment authentication or
  multi-server coordination.

See [backend instructions and protocol](../backend/README.md). The next stage can
build a dashboard against replay without implying that live room mapping is solved.
