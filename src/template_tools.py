from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple
import os

import cv2
import numpy as np


@dataclass
class TemplateResult:
    ok: bool
    bbox: Optional[Tuple[int, int, int, int]] = None
    image: Optional[np.ndarray] = None
    reason: str = ""


def _red_mask(bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    lower1 = np.array([0, 120, 120], dtype=np.uint8)
    upper1 = np.array([10, 255, 255], dtype=np.uint8)
    lower2 = np.array([170, 120, 120], dtype=np.uint8)
    upper2 = np.array([180, 255, 255], dtype=np.uint8)
    m1 = cv2.inRange(hsv, lower1, upper1)
    m2 = cv2.inRange(hsv, lower2, upper2)
    mask = cv2.bitwise_or(m1, m2)
    mask = cv2.medianBlur(mask, 3)
    return mask


def extract_red_word_template(bgr: np.ndarray) -> TemplateResult:
    """Try to extract a red word-like region (e.g., Wendigo) from a full screenshot.

    Heuristic-based: finds connected components on a red hue mask, keeps the
    widest component with text-like aspect ratio and reasonable size.
    """
    mask = _red_mask(bgr)
    # Morph to join characters
    kernel = np.ones((3, 3), np.uint8)
    mask = cv2.dilate(mask, kernel, iterations=1)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cand = None
    best_score = -1.0
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        area = w * h
        if area < 200:  # ignore tiny noise
            continue
        ar = w / max(1, h)
        # Word-like aspect ratio and size gate
        if 2.2 <= ar <= 10.0 and 14 <= h <= 120:
            score = area * ar  # prefer wider/clearer candidates
            if score > best_score:
                best_score = score
                cand = (x, y, w, h)

    if not cand:
        return TemplateResult(False, reason="no suitable red word region found")

    x, y, w, h = cand
    pad_x = max(2, int(0.06 * w))
    pad_y = max(2, int(0.2 * h))
    x0 = max(0, x - pad_x)
    y0 = max(0, y - pad_y)
    x1 = min(bgr.shape[1], x + w + pad_x)
    y1 = min(bgr.shape[0], y + h + pad_y)
    crop = bgr[y0:y1, x0:x1].copy()
    return TemplateResult(True, (x0, y0, x1 - x0, y1 - y0), crop, "heuristic-red")


def save_template(img: np.ndarray, out_path: str) -> None:
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    cv2.imwrite(out_path, img)

