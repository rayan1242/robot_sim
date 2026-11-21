import multiprocessing as mp
from queue import Empty
import threading
import time

from .protocol import packet
from .worker import camera_worker, replay_worker


class Runtime:
    def __init__(self, store):
        self.store = store
        self.context = mp.get_context("spawn")
        self.lock = threading.RLock()
        self.process = None
        self.current = None
        self.queue = None
        self.stop_event = None
        self.latest = packet({"state": "idle", "mode": None})
        self.revision = 0
        self.shutdown_event = threading.Event()
        self.monitor = threading.Thread(target=self._monitor, daemon=True)
        self.monitor.start()

    def start(self, identifier, mode, options):
        with self.lock:
            if self.process is not None:
                raise RuntimeError("Another pipeline is active; stop it first")
            self.store.get(identifier)
            self.queue = self.context.Queue(maxsize=1)
            self.stop_event = self.context.Event()
            self.current = identifier
            target = camera_worker if mode == "live" else replay_worker
            arguments = ((self.store.path(identifier), options, self.queue, self.stop_event) if mode == "live" else
                         (self.store.path(identifier), self.queue, self.stop_event, options["speed"]))
            self.process = self.context.Process(target=target, args=arguments, daemon=True)
            self.latest = packet({"state": "starting", "mode": mode, "session_id": identifier})
            self.revision += 1
            self.store.update(identifier, "recording" if mode == "live" else "replaying")
            try:
                self.process.start()
            except Exception:
                self.queue.close()
                self.process = self.current = None
                self.store.update(identifier, "error")
                raise

    def snapshot(self):
        with self.lock:
            return self.revision, self.latest

    def _finish(self, forced=False):
        identifier = self.current
        mode = self.latest[0].get("mode")
        failed = (forced or self.process.exitcode not in (0, None) or
                  self.latest[0].get("state") == "error" or
                  (self.store.path(identifier)/"error.txt").exists())
        state, jpeg, cloud = self.latest
        saved = self.store.get(identifier)
        metadata = saved["metadata"]
        if mode == "live":
            if 'map_snapshot_saved' in state:
                metadata.update(map_snapshot_saved=state['map_snapshot_saved'],map_snapshot_warning=state.get('map_snapshot_warning'))
            metadata.update(actual_image_size_wh=state.get("image_size_wh"),
                            actual_device=state.get("device"), model=state.get("model"),
                            saved_rgb_frames=sum(1 for _ in (self.store.path(identifier)/"rgb").glob("*.png")))
        self.store.update(identifier, "error" if failed else "ready", metadata)
        self.latest = ({**state, "session_id": identifier, "state": "error" if failed else "completed",
                        "mode": mode, "stopped": bool(self.stop_event.is_set())}, jpeg, cloud)
        self.revision += 1
        self.process.join(timeout=0)
        self.queue.close()
        self.process = self.current = self.queue = self.stop_event = None

    def _monitor(self):
        while not self.shutdown_event.wait(0.01):
            with self.lock:
                if self.process is None:
                    continue
                try:
                    while True:
                        state, jpeg, cloud = self.queue.get_nowait()
                        self.latest = ({**state, "session_id": self.current}, jpeg, cloud)
                        self.revision += 1
                except Empty:
                    pass
                if not self.process.is_alive():
                    self._finish()

    def stop(self, identifier):
        with self.lock:
            if self.current != identifier or self.process is None:
                raise RuntimeError("This session is not active")
            process = self.process
            self.stop_event.set()
        # Monitor keeps draining IPC while waiting for the worker to flush/exit.
        process.join(timeout=5)
        with self.lock:
            if self.process is process:
                forced = process.is_alive()
                if forced:
                    process.terminate()
                    process.join(timeout=2)
                self._finish(forced=forced)
        return self.store.get(identifier)

    def close(self):
        with self.lock:
            identifier = self.current
        if identifier:
            try:
                self.stop(identifier)
            except RuntimeError:
                pass
        self.shutdown_event.set()
        self.monitor.join(timeout=2)
