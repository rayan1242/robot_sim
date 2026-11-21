import asyncio
from contextlib import asynccontextmanager
import os
from pathlib import Path
import shutil
import tempfile
import zipfile

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import StreamingResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .runtime import Runtime
from .store import SessionStore


class StartRequest(BaseModel):
    name: str = Field(default="Webcam recording", min_length=1, max_length=120)
    camera: int = Field(default=0, ge=0, le=20)
    width: int = Field(default=640, ge=64, le=1920)
    height: int = Field(default=480, ge=64, le=1080)
    fps: float = Field(default=15, gt=0, le=120)
    duration: float = Field(default=30, gt=0, le=600)
    backend: str = Field(default="dshow", pattern="^(dshow|msmf|auto)$")
    depth: bool = False
    device: str = Field(default="auto", pattern="^(auto|cpu|cuda)$")
    auto_exposure: bool = True
    depth_width: int = Field(default=320,ge=112,le=640)
    depth_height: int = Field(default=240,ge=84,le=480)
    deadline_ms: float = Field(default=500,gt=0,le=10000)
    slam: bool = False
    keyframe_map: bool = False


class ReplayRequest(BaseModel):
    speed: float = Field(default=1, ge=0.1, le=10)


def create_app(root=None):
    initialization_profile=os.environ.get('ROBOT_SLAM_INITIALIZATION','baseline')
    if initialization_profile not in ('baseline','strict'):
        raise ValueError('ROBOT_SLAM_INITIALIZATION must be baseline or strict')
    @asynccontextmanager
    async def lifespan(app):
        app.state.store = SessionStore(root or os.environ.get("ROBOT_SESSION_ROOT", "data/sessions"))
        for session in app.state.store.list():
            if session["status"] in ("recording", "replaying"):
                app.state.store.update(session["id"], "interrupted")
        app.state.runtime = Runtime(app.state.store)
        yield
        await asyncio.to_thread(app.state.runtime.close)

    app = FastAPI(title="Monocular perception sessions", version="0.1.0", lifespan=lifespan)

    def get_session(identifier):
        try:
            return app.state.store.get(identifier)
        except KeyError:
            raise HTTPException(404, "Session not found")

    @app.get("/health")
    def health():
        revision, current = app.state.runtime.snapshot()
        return {"status": "ok", "stream": current[0], "revision": revision,
                "slam_initialization_profile": initialization_profile}

    @app.get("/sessions")
    def sessions():
        return app.state.store.list()

    @app.get("/sessions/{identifier}")
    def session(identifier: str):
        return get_session(identifier)

    @app.post("/sessions/start", status_code=201)
    def start(request: StartRequest):
        runtime = app.state.runtime
        with runtime.lock:
            if runtime.process is not None:
                raise HTTPException(409, "Another pipeline is active")
            options = request.model_dump()
            if options['keyframe_map']:options['slam']=True
            if options['slam']:
                if (request.width,request.height)!=(640,480):raise HTTPException(422,'Live SLAM requires calibrated 640x480 capture')
                options['depth']=True
                options['slam_initialization_profile']=initialization_profile
                options['slam_config']=str(Path(__file__).resolve().parents[1]/'slam'/
                    ('webcam_640_mono_strict.yaml' if initialization_profile=='strict' else 'webcam_640_mono.yaml'))
            saved = app.state.store.create(request.name, {"source": "webcam", "options": options,
                "limitations": ["Live camera/depth only; no live SLAM/fusion", "Depth has no metric scale",
                                "AVI uses configured FPS; timestamps.csv is authoritative for timing"]})
            if options['slam']:
                app.state.store.update(saved['id'],saved['status'],{**saved['metadata'],'limitations':[
                    'Experimental live SLAM; initialization/tracking may fail',
                    'Global sparse map plus current local dense preview; historical dense patches are not accumulated',
                    'Arbitrary SLAM units, not meters; fits do not establish independent accuracy']})
                if options['keyframe_map']:
                    current=app.state.store.get(saved['id'])
                    limits=current['metadata']['limitations']
                    limits[1]='Bounded cross-view-validated keyframe window rebuilt with current poses; not complete room reconstruction'
                    app.state.store.update(saved['id'],current['status'],{**current['metadata'],'limitations':limits})
            try:
                runtime.start(saved["id"], "live", options)
            except RuntimeError as exc:
                raise HTTPException(409, str(exc))
            return app.state.store.get(saved["id"])

    @app.post("/sessions/{identifier}/stop")
    def stop(identifier: str):
        get_session(identifier)
        try:
            return app.state.runtime.stop(identifier)
        except RuntimeError as exc:
            raise HTTPException(409, str(exc))

    @app.get("/sessions/{identifier}/preview")
    def preview(identifier: str):
        import json
        get_session(identifier)
        directory = app.state.store.path(identifier)
        states = directory/"states.jsonl"
        if not states.exists():
            raise HTTPException(404, "Session has no camera preview yet")
        with states.open(encoding="utf-8") as handle:
            first = handle.readline()
        try:
            image = (directory/json.loads(first)["rgb_path"]).resolve()
        except (ValueError, KeyError):
            raise HTTPException(404, "Session has no valid camera preview")
        if not image.is_relative_to(directory) or not image.is_file():
            raise HTTPException(404, "Preview is unavailable")
        return FileResponse(image, media_type="image/png")

    @app.get("/sessions/{identifier}/snapshot")
    def snapshot(identifier: str):
        from .protocol import encode_cloud
        get_session(identifier)
        _,(state,_,live_cloud)=app.state.runtime.snapshot()
        if state.get('session_id')==identifier and state.get('cloud_semantics')=='live_sparse_and_local_dense':
            return Response(live_cloud,media_type='application/octet-stream',headers={
                'X-Point-Count':str(state.get('cloud_point_count',0)),'Cache-Control':'no-store'})
        path = app.state.store.path(identifier)/"map.npz"
        if not path.exists():
            raise HTTPException(404, "Session has no saved map")
        try:
            content, count = encode_cloud(path)
        except ValueError:
            raise HTTPException(422, "Saved map is invalid")
        return Response(content, media_type="application/octet-stream",
                        headers={"X-Point-Count": str(count), "Cache-Control": "no-store"})

    @app.get("/sessions/{identifier}/analysis")
    def analysis(identifier: str):
        import json
        get_session(identifier)
        path = app.state.store.path(identifier)/"analysis.json"
        return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {"tracking":None,"fusion":None}

    @app.get("/sessions/{identifier}/depth/{sequence}")
    def depth_preview(identifier: str, sequence: int):
        import cv2
        import numpy as np
        from perception.depth import colorize_depth
        get_session(identifier)
        if sequence < 0 or sequence > 1000000:
            raise HTTPException(404, "Depth frame is unavailable")
        path = app.state.store.path(identifier)/f"depth_{sequence:06d}.npy"
        if not path.is_file():
            raise HTTPException(404, "Relative depth was not recorded for this frame")
        with path.open("rb") as handle:
            depth = np.load(handle, allow_pickle=False)
        if depth.ndim != 2:
            raise HTTPException(422, "Invalid depth frame")
        ok, encoded = cv2.imencode(".png", colorize_depth(depth))
        if not ok:
            raise HTTPException(422, "Depth image could not be encoded")
        return Response(encoded.tobytes(), media_type="image/png")

    @app.post("/sessions/{identifier}/replay")
    def replay(identifier: str, request: ReplayRequest):
        get_session(identifier)
        if not (app.state.store.path(identifier)/"states.jsonl").exists():
            raise HTTPException(409, "Session has no replayable states")
        try:
            app.state.runtime.start(identifier, "replay", {"speed": request.speed})
        except RuntimeError as exc:
            raise HTTPException(409, str(exc))
        return app.state.store.get(identifier)

    @app.delete("/sessions/{identifier}")
    def delete(identifier: str):
        get_session(identifier)
        with app.state.runtime.lock:
            if app.state.runtime.current == identifier:
                raise HTTPException(409, "Stop the session before deleting")
            directory = app.state.store.path(identifier)
            if directory.parent != app.state.store.root:
                raise HTTPException(400, "Invalid session path")
            shutil.rmtree(directory)
            with app.state.store.connect() as db:
                db.execute("DELETE FROM sessions WHERE id=?", (identifier,))
        return {"deleted": identifier}

    @app.get("/sessions/{identifier}/download")
    def download(identifier: str):
        metadata = get_session(identifier)
        if app.state.runtime.current == identifier:
            raise HTTPException(409, "Stop the session before downloading")

        def archive():
            import json
            with tempfile.TemporaryFile() as handle:
                with zipfile.ZipFile(handle, "w", compression=zipfile.ZIP_STORED) as bundle:
                    bundle.writestr("session.json", json.dumps(metadata, indent=2))
                    directory = app.state.store.path(identifier)
                    for path in directory.rglob("*"):
                        if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(directory):
                            bundle.write(path, path.relative_to(directory).as_posix())
                handle.seek(0)
                while chunk := handle.read(1024*1024):
                    yield chunk
        return StreamingResponse(archive(), media_type="application/zip",
                                 headers={"Content-Disposition": f'attachment; filename="{identifier}.zip"'})

    @app.websocket("/ws/live")
    async def stream(socket: WebSocket):
        await socket.accept()
        last_revision = -1
        try:
            while True:
                revision, (state, jpeg, cloud) = app.state.runtime.snapshot()
                if revision != last_revision:
                    header = {**state, "stream_revision": revision,
                              "subscriber_skipped_updates": max(0, revision-last_revision-1) if last_revision >= 0 else 0}
                    if state.get('mode')=='live' and state.get('state')=='running' and state.get('capture_receipt_monotonic') is not None:
                        import time
                        header['capture_receipt_to_server_send_ms']=max(0,(time.perf_counter()-state['capture_receipt_monotonic'])*1000)
                    # A stalled client is disconnected without affecting the worker.
                    await asyncio.wait_for(socket.send_json(header), timeout=5)
                    if jpeg:
                        await asyncio.wait_for(socket.send_bytes(jpeg), timeout=5)
                    if cloud:
                        await asyncio.wait_for(socket.send_bytes(cloud), timeout=5)
                    last_revision = revision
                # Receive with timeout notices disconnects even when the source is idle.
                try:
                    message = await asyncio.wait_for(socket.receive(), timeout=0.02)
                    if message["type"] == "websocket.disconnect":
                        return
                except asyncio.TimeoutError:
                    pass
        except (WebSocketDisconnect, asyncio.TimeoutError, RuntimeError):
            return

    frontend = Path(__file__).resolve().parents[1]/"frontend"
    if frontend.is_dir():
        # API and WebSocket routes above retain priority; dashboard assets share the same origin.
        app.mount("/", StaticFiles(directory=frontend, html=True), name="dashboard")
    return app


app = create_app()
