from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import cv2
import numpy as np
import pytesseract

from bsbot.platform import capture
from bsbot.platform import input as human_input


@dataclass
class MinimapSettings:
    toggle_key: str = "m"
    roi: Tuple[float, float, float, float] = (0.74, 0.1, 0.22, 0.32)
    coords_roi: Tuple[float, float, float, float] = (0.79, 0.4, 0.16, 0.1)
    anchor_interval_s: float = 45.0
    open_delay_s: float = 0.45
    close_delay_s: float = 0.25


@dataclass
class MinimapAnchor:
    world_tile: Optional[Tuple[int, int]]
    raw_text: str
    confidence: float


class MinimapManager:
    """Automates minimap toggling to capture absolute coordinates."""

    def __init__(self, runtime, *, settings: MinimapSettings) -> None:
        self.runtime = runtime
        self.settings = settings
        self._last_anchor_ts: float = 0.0

    def maybe_anchor(self, window_rect: Tuple[int, int, int, int]) -> None:
        if self.settings.anchor_interval_s <= 0:
            return
        now = time.time()
        if now - self._last_anchor_ts < self.settings.anchor_interval_s:
            return
        anchor = self._capture_anchor(window_rect)
        self._last_anchor_ts = now
        if anchor:
            self.runtime.update_minimap_anchor(anchor)

    def _capture_anchor(self, window_rect: Tuple[int, int, int, int]) -> Optional[MinimapAnchor]:
        toggle = self.settings.toggle_key
        if not toggle:
            return None
        try:
            human_input.human_keypress(toggle, hold=0.08)
        except Exception as exc:
            self.runtime.logger.exception("minimap open failed | key=%s error=%s", toggle, exc)
            return None
        time.sleep(self.settings.open_delay_s)
        frame = self._grab_roi(window_rect, self.settings.roi)
        coords_roi = self._extract_coords_roi(frame)
        anchor = self._read_coordinates(coords_roi)
        try:
            human_input.human_keypress(toggle, hold=0.08)
        except Exception as exc:
            self.runtime.logger.exception("minimap close failed | key=%s error=%s", toggle, exc)
        time.sleep(self.settings.close_delay_s)
        if anchor:
            self.runtime.emit_event(
                "calibration",
                "minimap_anchor",
                [0, 0, 0, 0],
                [],
                anchor.confidence,
                notes=f"tile={anchor.world_tile} raw={anchor.raw_text.strip()}",
            )
        return anchor

    def _grab_roi(self, window_rect: Tuple[int, int, int, int], roi: Tuple[float, float, float, float]) -> np.ndarray:
        x, y, w, h = window_rect
        rx, ry, rw, rh = roi
        ax = int(x + rx * w)
        ay = int(y + ry * h)
        aw = max(1, int(rw * w))
        ah = max(1, int(rh * h))
        return capture.grab_rect(ax, ay, aw, ah)

    def _extract_coords_roi(self, minimap_frame: np.ndarray) -> np.ndarray:
        h, w = minimap_frame.shape[:2]
        rx, ry, rw, rh = self.settings.coords_roi
        x = int(rx * w)
        y = int(ry * h)
        ww = max(1, int(rw * w))
        hh = max(1, int(rh * h))
        x = max(0, min(w - 1, x))
        y = max(0, min(h - 1, y))
        ww = min(ww, w - x)
        hh = min(hh, h - y)
        return minimap_frame[y : y + hh, x : x + ww]

    def _read_coordinates(self, frame: np.ndarray) -> Optional[MinimapAnchor]:
        if frame.size == 0:
            return None
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_OTSU)
        config = "--psm 6 -l eng -c tessedit_char_whitelist=0123456789,/- "
        try:
            text = pytesseract.image_to_string(thresh, config=config)
        except Exception:
            return None
        numbers = re.findall(r"(-?\d+)", text)
        if len(numbers) >= 2:
            try:
                x_val = int(numbers[0])
                y_val = int(numbers[1])
            except ValueError:
                return MinimapAnchor(None, text, 0.0)
            return MinimapAnchor((x_val, y_val), text, 0.75)
        return MinimapAnchor(None, text, 0.0)
