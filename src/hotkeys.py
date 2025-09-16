from __future__ import annotations

import threading
import time
from typing import Optional, Callable

import ctypes
from ctypes import wintypes


class HotkeyManager:
    def __init__(self, on_pause_toggle: Callable[[], None], on_kill: Callable[[], None]):
        self.on_pause_toggle = on_pause_toggle
        self.on_kill = on_kill
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        # Best-effort unhook for keyboard library if it was used
        try:
            import keyboard  # type: ignore
            keyboard.unhook_all_hotkeys()
        except Exception:
            pass

    def _worker(self) -> None:
        # First try the 'keyboard' library; if unavailable, fall back to Win32 RegisterHotKey
        try:
            import keyboard  # type: ignore
            keyboard.add_hotkey('ctrl+alt+p', lambda: self.on_pause_toggle())
            keyboard.add_hotkey('ctrl+alt+o', lambda: self.on_kill())
            self._stop.wait()
            return
        except Exception:
            pass

        user32 = ctypes.windll.user32
        MOD_ALT = 0x0001
        MOD_CONTROL = 0x0002
        VK_P = 0x50
        VK_O = 0x4F
        WM_HOTKEY = 0x0312
        PM_REMOVE = 0x0001

        # Define MSG struct
        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        class MSG(ctypes.Structure):
            _fields_ = [
                ("hwnd", wintypes.HWND),
                ("message", wintypes.UINT),
                ("wParam", wintypes.WPARAM),
                ("lParam", wintypes.LPARAM),
                ("time", wintypes.DWORD),
                ("pt", POINT),
            ]

        # Register hotkeys
        user32.RegisterHotKey(None, 1, MOD_CONTROL | MOD_ALT, VK_P)
        user32.RegisterHotKey(None, 2, MOD_CONTROL | MOD_ALT, VK_O)

        msg = MSG()
        try:
            while not self._stop.is_set():
                if user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                    if msg.message == WM_HOTKEY:
                        if msg.wParam == 1:
                            try: self.on_pause_toggle()
                            except Exception: pass
                        elif msg.wParam == 2:
                            try: self.on_kill()
                            except Exception: pass
                time.sleep(0.05)
        finally:
            user32.UnregisterHotKey(None, 1)
            user32.UnregisterHotKey(None, 2)
