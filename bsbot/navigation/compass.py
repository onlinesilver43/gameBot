from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np

from bsbot.platform import capture
from bsbot.platform import input as human_input


@dataclass
class CompassSettings:
    roi: Tuple[float, float, float, float]
    align_threshold_deg: float = 5.0
    drift_threshold_deg: float = 8.0
    sample_interval_s: float = 2.5
    rotate_keys: Tuple[str, str] = ("left", "right")
    rotation_rate_deg_s: float = 120.0
    rotation_hold_s: float = 0.16
    max_samples: int = 5


class CompassCalibrator:
    """Detects compass needle orientation within a frame."""

    def __init__(self, *, min_area: float = 150.0, blur: int = 3) -> None:
        self.min_area = min_area
        self.blur = blur

    def detect_angle(self, frame: np.ndarray) -> Optional[float]:
        if frame.size == 0:
            return None
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        lower1 = np.array([0, 110, 120], dtype=np.uint8)
        upper1 = np.array([12, 255, 255], dtype=np.uint8)
        lower2 = np.array([168, 110, 120], dtype=np.uint8)
        upper2 = np.array([180, 255, 255], dtype=np.uint8)
        mask1 = cv2.inRange(hsv, lower1, upper1)
        mask2 = cv2.inRange(hsv, lower2, upper2)
        mask = cv2.bitwise_or(mask1, mask2)
        if self.blur > 0:
            k = max(1, self.blur // 2 * 2 + 1)
            mask = cv2.GaussianBlur(mask, (k, k), 0)
        _, mask = cv2.threshold(mask, 100, 255, cv2.THRESH_BINARY)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None
        contour = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(contour)
        if area < self.min_area:
            return None
        m = cv2.moments(contour)
        if m["m00"] == 0:
            return None
        cx = float(m["m10"] / m["m00"])
        cy = float(m["m01"] / m["m00"])
        pts = contour.reshape(-1, 2).astype(np.float32)
        distances = np.linalg.norm(pts - np.array([cx, cy], dtype=np.float32), axis=1)
        idx = int(np.argmax(distances))
        tip = pts[idx]
        dx = float(tip[0] - cx)
        dy = float(tip[1] - cy)
        if dx == 0 and dy == 0:
            return None
        # Angle relative to vertical up direction (North)
        angle_rad = math.atan2(dx, -dy)
        angle_deg = math.degrees(angle_rad)
        return float(angle_deg)


class CompassManager:
    """Controls camera alignment based on compass orientation."""

    def __init__(
        self,
        runtime,
        *,
        settings: CompassSettings,
        calibrator: Optional[CompassCalibrator] = None,
    ) -> None:
        self.runtime = runtime
        self.settings = settings
        self.calibrator = calibrator or CompassCalibrator()
        self._last_sample_ts = 0.0
        self._last_angle: Optional[float] = None
        self._last_align_ts: Optional[float] = None
        self._aligning = False

    def ensure_aligned(self, window_rect: Tuple[int, int, int, int]) -> None:
        now = time.time()
        if now - self._last_sample_ts < self.settings.sample_interval_s:
            return
        angle = self._sample_angle(window_rect)
        self._last_sample_ts = now
        if angle is None:
            return
        self._last_angle = angle
        self.runtime.update_compass_status(angle=angle)
        threshold = self.settings.align_threshold_deg if not self._aligning else self.settings.drift_threshold_deg
        if abs(angle) <= threshold:
            self._last_align_ts = now
            self.runtime.update_compass_status(aligned=True)
            return
        self._aligning = True
        self._perform_alignment(angle, window_rect)
        self._aligning = False

    def _sample_angle(self, window_rect: Tuple[int, int, int, int]) -> Optional[float]:
        x, y, w, h = window_rect
        rx, ry, rw, rh = self.settings.roi
        ax = int(x + rx * w)
        ay = int(y + ry * h)
        aw = int(rw * w)
        ah = int(rh * h)
        if aw <= 0 or ah <= 0:
            return None
        frame = capture.grab_rect(ax, ay, aw, ah)
        return self.calibrator.detect_angle(frame)

    def _perform_alignment(self, angle: float, window_rect: Tuple[int, int, int, int]) -> None:
        rotate_left, rotate_right = self.settings.rotate_keys
        key = rotate_left if angle > 0 else rotate_right
        rate = max(10.0, self.settings.rotation_rate_deg_s)
        hold = min(0.8, max(self.settings.rotation_hold_s, abs(angle) / rate))
        try:
            human_input.human_keypress(key, hold=hold)
        except Exception as exc:
            self.runtime.logger.exception("compass align failed | angle=%.2f key=%s error=%s", angle, key, exc)
            return
        self.runtime.logger.info("compass_align | angle=%.2f key=%s hold=%.2f", angle, key, hold)
        self.runtime.emit_event(
            "calibration",
            "compass_align",
            [0, 0, 0, 0],
            [],
            0.0,
            notes=f"angle={angle:.2f} key={key} hold={hold:.2f}",
        )
        time.sleep(hold + 0.1)
        # Re-sample to confirm alignment
        resample = self._sample_angle(window_rect)
        if resample is not None:
            self.runtime.update_compass_status(angle=resample, aligned=abs(resample) <= self.settings.align_threshold_deg)
