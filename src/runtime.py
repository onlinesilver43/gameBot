from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Optional, Tuple

import cv2
import os

from . import window as win
from . import capture
from .detect import detect_word_ocr, detect_with_template, configure_tesseract
from .logging_setup import init_logging


@dataclass
class DetectionStatus:
    running: bool = False
    paused: bool = False
    last_result: dict = field(default_factory=dict)
    last_frame: Optional[bytes] = None  # JPEG bytes for preview
    template_path: Optional[str] = None
    title: str = "Brighter Shores"
    word: str = "Wendigo"
    tesseract_path: Optional[str] = None
    roi: Tuple[float, float, float, float] = (0.2, 0.25, 0.6, 0.5)  # relative ROI
    total_detections: int = 0


class DetectorRuntime:
    def __init__(self) -> None:
        self.logger = init_logging(level=os.environ.get("LOG_LEVEL", "INFO"))
        self.status = DetectionStatus()
        # pick up TESSERACT_PATH default if present
        self.status.tesseract_path = os.environ.get("TESSERACT_PATH") or None
        self._thread: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()
        self._lock = threading.Lock()

    def start(self, title: Optional[str] = None, word: Optional[str] = None, template_path: Optional[str] = None, tesseract_path: Optional[str] = None) -> None:
        with self._lock:
            if self.status.running:
                # Update parameters while running
                if title: self.status.title = title
                if word: self.status.word = word
                if template_path: self.status.template_path = template_path
                if tesseract_path: self.status.tesseract_path = tesseract_path
                self.status.paused = False
                self.logger.info("Runtime updated | title=%s word=%s template=%s", self.status.title, self.status.word, self.status.template_path)
                return
            if title: self.status.title = title
            if word: self.status.word = word
            self.status.template_path = template_path
            self.status.tesseract_path = tesseract_path
            self.status.running = True
            self.status.paused = False
            self._stop_evt.clear()
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
            self.logger.info("Runtime started | title=%s word=%s template=%s", self.status.title, self.status.word, self.status.template_path)

    def pause(self) -> None:
        with self._lock:
            if self.status.running:
                self.status.paused = True
                self.logger.info("Runtime paused")

    def stop(self) -> None:
        with self._lock:
            self._stop_evt.set()
            self.status.running = False
            self.status.paused = False
            self.logger.info("Runtime stopped")

    def _run_loop(self) -> None:
        win.make_dpi_aware()
        # Configure tesseract once per loop if using OCR
        if not self.status.template_path:
            configure_tesseract(self.status.tesseract_path)
        last_log_t = 0.0
        last_found = None
        while not self._stop_evt.is_set():
            if self.status.paused:
                time.sleep(0.1)
                continue
            try:
                hwnd = win.find_window_exact(self.status.title)
                if not hwnd:
                    msg = {"error": f"Window not found: {self.status.title}"}
                    self._set_result(msg, frame=None)
                    now = time.time()
                    if now - last_log_t > 2.0:
                        self.logger.warning("%s", msg["error"]) 
                        last_log_t = now
                    time.sleep(0.5)
                    continue
                x, y, w, h = win.get_client_rect(hwnd)
                rx, ry, rw, rh = self._roi_pixels(x, y, w, h)
                frame = capture.grab_rect(rx, ry, rw, rh)
                boxes = []
                best_conf = 0.0
                method = ""
                if self.status.template_path:
                    tpl = cv2.imread(self.status.template_path, cv2.IMREAD_COLOR)
                    if tpl is None:
                        self.logger.warning("template not readable at %s, falling back to OCR", self.status.template_path)
                    else:
                        from .detect import detect_template_multi
                        boxes, scores = detect_template_multi(frame, tpl)
                        best_conf = max(scores) if scores else 0.0
                        method = "template"
                if not boxes:
                    from .detect import detect_word_ocr_multi
                    boxes, best_conf = detect_word_ocr_multi(frame, target=self.status.word)
                    method = "ocr"

                annotated = frame.copy()
                for (bx, by, bw, bh) in boxes:
                    cv2.rectangle(annotated, (bx, by), (bx + bw, by + bh), (0, 0, 255), 2)
                ok, jpg = cv2.imencode('.jpg', annotated)
                preview = jpg.tobytes() if ok else None

                count = len(boxes)
                if count:
                    self.status.total_detections += count
                self._set_result({
                    "found": count > 0,
                    "count": count,
                    "confidence": best_conf,
                    "method": method,
                    "boxes": boxes,
                    "total_detections": self.status.total_detections,
                    "roi": [rx, ry, rw, rh],
                }, preview)
                now = time.time()
                if last_found is not (count > 0) or now - last_log_t > 2.0:
                    self.logger.info("detect | found=%s count=%d conf=%.3f method=%s", count > 0, count, best_conf, method)
                    last_log_t = now
                    last_found = count > 0
            except Exception as e:
                self._set_result({"error": str(e)}, frame=None)
                self.logger.exception("runtime error")
            time.sleep(0.3)

    def _roi_pixels(self, x: int, y: int, w: int, h: int) -> Tuple[int, int, int, int]:
        rx, ry, rw, rh = self.status.roi
        return int(x + rx * w), int(y + ry * h), int(rw * w), int(rh * h)

    def _set_result(self, result: dict, frame: Optional[bytes]) -> None:
        with self._lock:
            self.status.last_result = result
            if frame is not None:
                self.status.last_frame = frame

    def snapshot(self) -> DetectionStatus:
        with self._lock:
            # Shallow copy is enough for read-only
            return self.status
