from __future__ import annotations

from typing import Tuple
import mss
import numpy as np


def grab_rect(x: int, y: int, w: int, h: int) -> np.ndarray:
    with mss.mss() as sct:
        monitor = {"left": x, "top": y, "width": w, "height": h}
        img = sct.grab(monitor)
        # mss returns BGRA; convert to BGR numpy array
        arr = np.asarray(img)[:, :, :3]
        return arr.copy()

