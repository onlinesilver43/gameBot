from __future__ import annotations

import random
import time
from typing import Tuple

import win32api  # type: ignore
import win32con  # type: ignore


def click_screen(x: int, y: int, jitter_px: int = 0, delay_ms: int = 0) -> None:
    """Move cursor to (x,y) and left-click with optional jitter and delay."""
    if jitter_px:
        x += random.randint(-jitter_px, jitter_px)
        y += random.randint(-jitter_px, jitter_px)
    if delay_ms:
        time.sleep(delay_ms / 1000.0)
    win32api.SetCursorPos((int(x), int(y)))
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
    time.sleep(0.02)
    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)

