from __future__ import annotations

import logging
import os
import random
import time
from typing import Optional, Tuple

try:
    import ctypes
except ImportError:  # pragma: no cover
    ctypes = None  # type: ignore

if os.name == "nt" and ctypes is not None:
    user32 = ctypes.windll.user32
    INPUT_AVAILABLE = True
else:  # pragma: no cover
    user32 = None  # type: ignore
    INPUT_AVAILABLE = False

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
KEYEVENTF_KEYUP = 0x0002

VK_MAP = {
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "home": 0x24,
    "end": 0x23,
    "pageup": 0x21,
    "pagedown": 0x22,
    "insert": 0x2D,
    "delete": 0x2E,
}

logger = logging.getLogger("bot.input")


def _ensure_available() -> None:
    if not INPUT_AVAILABLE:
        raise RuntimeError("Human input simulation is only supported on Windows with ctypes available")


def _set_cursor_pos(x: int, y: int) -> None:
    _ensure_available()
    if not user32.SetCursorPos(int(x), int(y)):
        raise OSError("SetCursorPos failed")


def _mouse_event(event_flag: int) -> None:
    _ensure_available()
    user32.mouse_event(event_flag, 0, 0, 0, 0)  # type: ignore[arg-type]


def _linear_move(start: Tuple[int, int], end: Tuple[int, int], duration: float) -> None:
    if duration <= 0:
        _set_cursor_pos(end[0], end[1])
        return
    steps = max(1, int(duration / 0.01))
    sx, sy = start
    ex, ey = end
    for i in range(1, steps + 1):
        t = i / steps
        nx = int(round(sx + (ex - sx) * t))
        ny = int(round(sy + (ey - sy) * t))
        _set_cursor_pos(nx, ny)
        time.sleep(duration / steps)


def _resolve_vk(key: str) -> int:
    k = key.strip().lower()
    if not k:
        raise ValueError("Key cannot be empty")
    if k in VK_MAP:
        return VK_MAP[k]
    if len(k) == 1:
        return ord(k.upper())
    raise ValueError(f"Unsupported key: {key}")


def _key_down(vk: int) -> None:
    _ensure_available()
    user32.keybd_event(vk, 0, 0, 0)  # type: ignore[arg-type]


def _key_up(vk: int) -> None:
    _ensure_available()
    user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)  # type: ignore[arg-type]


def human_move(
    point: Tuple[int, int],
    *,
    jitter_px: int = 4,
    move_duration: float = 0.12,
    hwnd: Optional[int] = None,
    ensure_foreground: bool = True,
) -> None:
    """Move the cursor towards ``point`` without clicking."""

    _ensure_available()

    from bsbot.platform.win32 import window as win

    if hwnd and ensure_foreground:
        try:
            if win.get_foreground_window() != hwnd:
                win.bring_to_foreground(hwnd)
                time.sleep(0.05)
        except Exception:
            logger.exception("Unable to ensure foreground window before move")

    jitter_x = random.uniform(-jitter_px, jitter_px) if jitter_px else 0.0
    jitter_y = random.uniform(-jitter_px, jitter_px) if jitter_px else 0.0
    target_x = int(round(point[0] + jitter_x))
    target_y = int(round(point[1] + jitter_y))

    current_pos = win.get_cursor_pos()
    _linear_move(current_pos, (target_x, target_y), max(0.0, move_duration))
    logger.info("move | x=%d y=%d jitter=(%.2f,%.2f)", target_x, target_y, jitter_x, jitter_y)


def human_keypress(key: str, hold: float = 0.1) -> None:
    """Press and release a keyboard key with optional hold duration."""

    vk = _resolve_vk(key)
    _key_down(vk)
    time.sleep(max(0.0, hold))
    _key_up(vk)
    logger.info("keypress | key=%s hold=%.3f", key, hold)


def human_click(
    point: Tuple[int, int],
    *,
    jitter_px: int = 4,
    move_duration: float = 0.12,
    click_delay: float = 0.05,
    hwnd: Optional[int] = None,
    ensure_foreground: bool = True,
) -> None:
    """Perform a human-like left click around ``point``.

    Args:
        point: Absolute screen-space (x, y) target.
        jitter_px: Random +/- jitter applied to both axes before moving.
        move_duration: Approximate duration of the mouse move animation.
        click_delay: Delay between button down and button up.
        hwnd: Optional window handle that should be validated/focused.
        ensure_foreground: When True, attempt to bring ``hwnd`` to the foreground.
    """

    _ensure_available()

    from bsbot.platform.win32 import window as win

    if hwnd and ensure_foreground:
        try:
            if win.get_foreground_window() != hwnd:
                win.bring_to_foreground(hwnd)
                time.sleep(0.05)
        except Exception:
            logger.exception("Unable to ensure foreground window before click")

    jitter_x = random.uniform(-jitter_px, jitter_px) if jitter_px else 0.0
    jitter_y = random.uniform(-jitter_px, jitter_px) if jitter_px else 0.0
    target_x = int(round(point[0] + jitter_x))
    target_y = int(round(point[1] + jitter_y))

    current_pos = win.get_cursor_pos()
    _linear_move(current_pos, (target_x, target_y), max(0.0, move_duration))

    time.sleep(0.01)
    _mouse_event(MOUSEEVENTF_LEFTDOWN)
    time.sleep(max(0.01, click_delay))
    _mouse_event(MOUSEEVENTF_LEFTUP)
    logger.info("click | x=%d y=%d jitter=(%.2f,%.2f)", target_x, target_y, jitter_x, jitter_y)


__all__ = ["human_click", "human_keypress", "human_move"]
