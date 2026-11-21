"""Threaded, latest-frame-only webcam capture."""
from dataclasses import dataclass
import threading
import time

import cv2
import numpy as np


@dataclass(frozen=True)
class FramePacket:
    image: np.ndarray
    sequence: int
    captured_at: float


class CameraCapture:
    def __init__(self, camera=0, width=640, height=480, fps=30, backend="auto",
                 focus=0.0, exposure=None, auto_exposure=False):
        self.camera = camera
        self.width, self.height, self.fps = width, height, fps
        self.backend = {"auto": cv2.CAP_ANY, "dshow": cv2.CAP_DSHOW,
                        "msmf": cv2.CAP_MSMF}[backend]
        self.focus, self.exposure = focus, exposure
        if auto_exposure and exposure is not None:
            raise ValueError("Choose automatic exposure or a manual exposure value")
        self.auto_exposure = auto_exposure
        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._packet = None
        self._thread = None
        self.error = None
        self.settings = {}
        self.read_failures = 0
        self.capture_fps = 0.0

    def start(self, timeout=10):
        if self._thread is not None:
            raise RuntimeError("Create a new capture instance to restart")
        self._thread = threading.Thread(target=self._run, daemon=True, name="camera")
        self._thread.start()
        self.get_latest(timeout=timeout)
        return self

    def _run(self):
        cap = None
        try:
            cap = cv2.VideoCapture(self.camera, self.backend)
            if not cap.isOpened():
                raise RuntimeError(f"Cannot open camera {self.camera}; try another index/backend")
            requests = [("width", cv2.CAP_PROP_FRAME_WIDTH, self.width),
                        ("height", cv2.CAP_PROP_FRAME_HEIGHT, self.height),
                        ("fps", cv2.CAP_PROP_FPS, self.fps),
                        ("buffer_size", cv2.CAP_PROP_BUFFERSIZE, 1),
                        ("autofocus", cv2.CAP_PROP_AUTOFOCUS, 0),
                        ("focus", cv2.CAP_PROP_FOCUS, self.focus),
                        ("auto_exposure", cv2.CAP_PROP_AUTO_EXPOSURE,
                         (0.75 if self.auto_exposure else 0.25) if cap.getBackendName() == "V4L2" else int(self.auto_exposure))]
            if self.exposure is not None:
                requests.append(("exposure", cv2.CAP_PROP_EXPOSURE, self.exposure))
            self.settings["backend"] = cap.getBackendName()
            for name, prop, value in requests:
                accepted = cap.set(prop, value)
                self.settings[name] = {"requested": value, "set_accepted": bool(accepted),
                                       "reported": cap.get(prop)}
            sequence, consecutive_failures = 0, 0
            last_time = None
            while not self._stop.is_set():
                ok, frame = cap.read()
                captured_at = time.perf_counter()
                if not ok or frame is None:
                    self.read_failures += 1
                    consecutive_failures += 1
                    if consecutive_failures >= 10:
                        raise RuntimeError("Camera failed to return 10 consecutive frames")
                    self._stop.wait(0.05)
                    continue
                consecutive_failures = 0
                if last_time is not None:
                    instantaneous = 1 / max(captured_at - last_time, 1e-9)
                    self.capture_fps = (instantaneous if not self.capture_fps else
                                        0.9 * self.capture_fps + 0.1 * instantaneous)
                last_time = captured_at
                frame.flags.writeable = False
                packet = FramePacket(frame, sequence, captured_at)
                sequence += 1
                with self._condition:
                    self._packet = packet
                    self._condition.notify_all()
        except Exception as exc:
            with self._condition:
                self.error = str(exc)
                self._condition.notify_all()
        finally:
            if cap is not None:
                cap.release()
            self._stop.set()
            with self._condition:
                self._condition.notify_all()

    def get_latest(self, after_sequence=-1, timeout=2):
        """Wait for a newer packet. Copy its image before modifying it."""
        deadline = time.perf_counter() + timeout
        with self._condition:
            while True:
                if self.error:
                    raise RuntimeError(self.error)
                if self._packet is not None and self._packet.sequence > after_sequence:
                    return self._packet
                if self._stop.is_set():
                    raise RuntimeError("Capture stopped")
                remaining = deadline - time.perf_counter()
                if remaining <= 0:
                    raise TimeoutError("Timed out waiting for a camera frame")
                self._condition.wait(remaining)

    def stop(self):
        self._stop.set()
        with self._condition:
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=3)
            if self._thread.is_alive():
                raise RuntimeError("Camera driver is blocked in read(); restart the process")

    def __enter__(self):
        try:
            return self.start()
        except Exception:
            self.stop()
            raise

    def __exit__(self, *args):
        self.stop()


def add_camera_arguments(parser):
    parser.add_argument("--camera", type=int, default=0)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--fps", type=float, default=30)
    parser.add_argument("--backend", choices=["auto", "dshow", "msmf"], default="auto")
    parser.add_argument("--focus", type=float, default=0)
    exposure = parser.add_mutually_exclusive_group()
    exposure.add_argument("--exposure", type=float)
    exposure.add_argument("--auto-exposure", action="store_true", help="Request automatic exposure for checking a dark feed; driver support varies")


def camera_from_args(args):
    return CameraCapture(**{key: getattr(args, key) for key in
                            ("camera", "width", "height", "fps", "backend", "focus", "exposure")},
                         auto_exposure=getattr(args,"auto_exposure",False))
