import ctypes
from ctypes import wintypes


class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32


def make_dpi_aware() -> None:
    try:
        user32.SetProcessDPIAware()
    except Exception:
        pass


def find_window_exact(title: str) -> int | None:
    hwnd = user32.FindWindowW(None, title)
    if hwnd:
        return hwnd
    return None


def get_client_rect(hwnd: int) -> tuple[int, int, int, int]:
    rect = RECT()
    if not user32.GetClientRect(hwnd, ctypes.byref(rect)):
        raise OSError("GetClientRect failed")

    pt = wintypes.POINT(rect.left, rect.top)
    if not user32.ClientToScreen(hwnd, ctypes.byref(pt)):
        raise OSError("ClientToScreen failed")

    left, top = pt.x, pt.y
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    return left, top, width, height


def bring_to_foreground(hwnd: int) -> None:
    try:
        user32.SetForegroundWindow(hwnd)
    except Exception:
        pass

