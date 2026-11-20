"""Tells whether the window in front covers the whole monitor (a game, a video)."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd"}  # the desktop and taskbar
MONITOR_DEFAULTTONEAREST = 2


class _MonitorInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def covers(win: tuple[int, int, int, int], mon: tuple[int, int, int, int]) -> bool:
    """True when rect `win` (left, top, right, bottom) hides all of `mon`."""
    return win[0] <= mon[0] and win[1] <= mon[1] and win[2] >= mon[2] and win[3] >= mon[3]


def foreground_is_fullscreen() -> bool:
    try:
        user32 = ctypes.windll.user32
        user32.GetForegroundWindow.restype = wintypes.HWND
        user32.MonitorFromWindow.restype = wintypes.HANDLE
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        name = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(wintypes.HWND(hwnd), name, 64)
        if name.value in SHELL_CLASSES:
            return False
        rect = wintypes.RECT()
        info = _MonitorInfo()
        info.cbSize = ctypes.sizeof(_MonitorInfo)
        monitor = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
        if not user32.GetWindowRect(wintypes.HWND(hwnd), ctypes.byref(rect)):
            return False
        if not user32.GetMonitorInfoW(wintypes.HANDLE(monitor), ctypes.byref(info)):
            return False
        m = info.rcMonitor
        return covers((rect.left, rect.top, rect.right, rect.bottom), (m.left, m.top, m.right, m.bottom))
    except (AttributeError, OSError):  # not Windows, or the call is unavailable
        return False
