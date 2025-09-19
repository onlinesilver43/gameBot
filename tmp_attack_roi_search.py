"""Brute-force ROI search for the attack button template.

Run with the project virtual environment, e.g.

    pwsh -NoLogo -Command "& {Set-Location 'C:\\gameAuto\\gameBot'; \
        . .\.venv\\Scripts\\Activate.ps1; python tmp_attack_roi_search.py}"
"""

from __future__ import annotations

import itertools
from typing import Dict, List, Tuple

import cv2
import numpy as np

from bsbot.vision.detect import detect_template_multi


SCREENSHOT_PATH = "assets/screenshots/screenshot_without_minimap_wendigo_attackButton.png"
TEMPLATE_PATH = "assets/templates/attack_button.png"


def main() -> None:
    frame = cv2.imread(SCREENSHOT_PATH, cv2.IMREAD_COLOR)
    if frame is None:
        raise SystemExit(f"Failed to load screenshot: {SCREENSHOT_PATH}")
    template = cv2.imread(TEMPLATE_PATH, cv2.IMREAD_COLOR)
    if template is None:
        raise SystemExit(f"Failed to load template: {TEMPLATE_PATH}")

    height, width = frame.shape[:2]

    rx_values = np.linspace(0.35, 0.55, 11)  # normalised x origin
    ry_values = np.linspace(0.25, 0.45, 11)  # normalised y origin
    rw_values = np.linspace(0.15, 0.30, 8)   # normalised width
    rh_values = np.linspace(0.10, 0.22, 7)   # normalised height

    results: List[Dict[str, object]] = []

    for rx, ry, rw, rh in itertools.product(rx_values, ry_values, rw_values, rh_values):
        x = int(round(rx * width))
        y = int(round(ry * height))
        w = int(round(rw * width))
        h = int(round(rh * height))

        if w <= 0 or h <= 0:
            continue
        if w < template.shape[1] or h < template.shape[0]:
            continue
        if x + w > width or y + h > height:
            continue

        roi = frame[y : y + h, x : x + w]
        boxes, scores = detect_template_multi(roi, template, threshold=0.7)
        if not scores:
            continue

        score = float(max(scores))
        if score < 0.85:
            continue

        results.append(
            {
                "score": score,
                "rx": rx,
                "ry": ry,
                "rw": rw,
                "rh": rh,
                "roi_px": (x, y, w, h),
                "boxes": boxes,
            }
        )

    if not results:
        print("No ROI exceeded score 0.85")
        return

    results.sort(key=lambda item: item["score"], reverse=True)

    print("Top ROI candidates (normalised coords):")
    for entry in results[:10]:
        rx = entry["rx"]
        ry = entry["ry"]
        rw = entry["rw"]
        rh = entry["rh"]
        score = entry["score"]
        x, y, w, h = entry["roi_px"]
        print(
            f" score={score:.3f} | rx={rx:.3f} ry={ry:.3f} rw={rw:.3f} rh={rh:.3f}"
            f" | roi_px=({x},{y},{w},{h})"
        )


if __name__ == "__main__":  # pragma: no cover
    main()
