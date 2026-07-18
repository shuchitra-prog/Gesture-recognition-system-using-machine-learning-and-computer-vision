# cv/camera_thread.py
# Background thread that continuously captures frames from the webcam.
# Decouples I/O latency from the processing pipeline.

import cv2
import threading
import time
from typing import Optional, Tuple
import numpy as np
from utils import get_logger
import config

logger = get_logger(__name__)


class CameraThread:
    """
    Runs OpenCV VideoCapture in a daemon thread.

    Usage
    -----
    cam = CameraThread()
    cam.start()
    frame = cam.read()   # always returns the most recent frame (or None)
    cam.stop()
    """

    def __init__(self,
                 index: int = config.CAMERA_INDEX,
                 width: int = config.CAMERA_WIDTH,
                 height: int = config.CAMERA_HEIGHT,
                 fps_limit: int = config.CAMERA_FPS_LIMIT):

        self.index     = index
        self.width     = width
        self.height    = height
        self.fps_limit = fps_limit

        self._cap:   Optional[cv2.VideoCapture] = None
        self._frame: Optional[np.ndarray]       = None
        self._lock   = threading.Lock()
        self._stop   = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.running = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Open webcam and start capture thread. Returns True on success."""
        self._cap = cv2.VideoCapture(self.index)
        if not self._cap.isOpened():
            logger.error("Cannot open camera index %d.", self.index)
            return False

        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH,  self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap.set(cv2.CAP_PROP_FPS, self.fps_limit)
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)  # minimal latency

        self._stop.clear()
        self.running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()
        logger.info("Camera thread started (index=%d, %dx%d).",
                    self.index, self.width, self.height)
        return True

    def stop(self):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        if self._cap:
            self._cap.release()
        self.running = False
        logger.info("Camera thread stopped.")

    # ── Frame access ──────────────────────────────────────────────────────────

    def read(self) -> Optional[np.ndarray]:
        """Return the most recent captured frame (BGR), or None."""
        with self._lock:
            return self._frame.copy() if self._frame is not None else None

    @property
    def frame_size(self) -> Tuple[int, int]:
        """(width, height) of captured frames."""
        return self.width, self.height

    # ── Capture loop (private) ────────────────────────────────────────────────

    def _capture_loop(self):
        interval = 1.0 / self.fps_limit
        failures = 0
        while not self._stop.is_set():
            t0 = time.perf_counter()
            ret, frame = self._cap.read()
            if ret:
                failures = 0
                frame = cv2.flip(frame, 1)          # mirror so it feels natural
                with self._lock:
                    self._frame = frame
            else:
                failures += 1
                if failures >= 30:
                    logger.error("Camera stopped returning frames; ending capture safely.")
                    self.running = False
                    break
            elapsed = time.perf_counter() - t0
            sleep_for = interval - elapsed
            if sleep_for > 0:
                time.sleep(sleep_for)
