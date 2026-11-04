"""Window metadata and pixel capture only; no accessibility selectors or app APIs."""
from __future__ import annotations
import ctypes
from ctypes import wintypes
from .screen import Frame, capture

u=ctypes.windll.user32
u.GetForegroundWindow.argtypes=[]
u.GetForegroundWindow.restype=wintypes.HWND
u.GetWindow.argtypes=[wintypes.HWND, wintypes.UINT]
u.GetWindow.restype=wintypes.HWND
u.GetWindowThreadProcessId.argtypes=[wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
u.GetWindowThreadProcessId.restype=wintypes.DWORD
u.IsWindow.argtypes=[wintypes.HWND]
u.GetClientRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
u.ClientToScreen.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.POINT)]
u.GetWindowTextLengthW.argtypes=[wintypes.HWND]
u.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
u.IsWindowVisible.argtypes=[wintypes.HWND]
u.IsIconic.argtypes=[wintypes.HWND]

def foreground() -> int:
    return int(u.GetForegroundWindow() or 0)

def list_windows() -> list[dict]:
    windows=[]
    callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    def visit(hwnd,_):
        length=u.GetWindowTextLengthW(hwnd)
        if length and u.IsWindowVisible(hwnd):
            title=ctypes.create_unicode_buffer(length+1)
            u.GetWindowTextW(hwnd,title,len(title))
            windows.append({'hwnd':int(hwnd),'title':title.value})
        return True
    if not u.EnumWindows(callback_type(visit),0):
        raise OSError('Could not enumerate windows')
    return windows

def _process_id(hwnd: int) -> int:
    pid = wintypes.DWORD()
    if not u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)):
        return 0
    return pid.value


class WindowTarget:
    """Scope input to a captured root or one of its owned modal windows."""
    def __init__(self, hwnd: int | None = None):
        self.hwnd = hwnd or foreground()
        if not self.hwnd or not u.IsWindow(self.hwnd):
            raise ValueError('Target window is not available')
        self.root_pid = _process_id(self.hwnd)
        self.observed_hwnd = None
        self.observed_rect = None

    def rect(self, hwnd: int | None = None):
        hwnd = self.hwnd if hwnd is None else hwnd
        rect = wintypes.RECT()
        origin = wintypes.POINT(0, 0)
        if not u.GetClientRect(hwnd, ctypes.byref(rect)) or not u.ClientToScreen(hwnd, ctypes.byref(origin)):
            raise OSError('Target window geometry is unavailable')
        return origin.x, origin.y, rect.right - rect.left, rect.bottom - rect.top

    def _in_scope(self, hwnd: int) -> bool:
        if not hwnd or not self.root_pid or not u.IsWindow(self.hwnd) or _process_id(self.hwnd) != self.root_pid:
            return False
        if not u.IsWindow(hwnd) or _process_id(hwnd) != self.root_pid:
            return False
        if not u.IsWindowVisible(hwnd) or u.IsIconic(hwnd):
            return False
        current = hwnd
        seen = set()
        # GW_OWNER = 4. Never follow an unbounded or cyclic owner chain.
        for _ in range(64):
            if current == self.hwnd:
                return True
            if not current or current in seen:
                return False
            seen.add(current)
            current = int(u.GetWindow(current, 4) or 0)
        return False

    def _rect_for(self, hwnd: int):
        return self.rect() if hwnd == self.hwnd else self.rect(hwnd)

    def guard(self):
        try:
            hwnd = self.observed_hwnd
            return (hwnd is not None and self.observed_rect is not None and
                    foreground() == hwnd and self._in_scope(hwnd) and
                    self._rect_for(hwnd) == self.observed_rect)
        except OSError:
            return False

    def capture(self) -> Frame:
        hwnd = foreground()
        if not self._in_scope(hwnd):
            raise RuntimeError('Foreground window is outside the target scope or unavailable')
        x, y, w, h = self._rect_for(hwnd)
        full = capture()
        if w <= 0 or h <= 0 or x < full.left or y < full.top or x + w > full.left + full.image.width or y + h > full.top + full.image.height:
            raise RuntimeError('Target must be fully visible on the primary capture display')
        if foreground() != hwnd or not self._in_scope(hwnd) or self._rect_for(hwnd) != (x, y, w, h):
            raise RuntimeError('Target changed during capture; reobserve before continuing')
        frame = Frame(full.image.crop((x - full.left, y - full.top, x - full.left + w, y - full.top + h)), x, y)
        self.observed_hwnd = hwnd
        self.observed_rect = (x, y, w, h)
        return frame
