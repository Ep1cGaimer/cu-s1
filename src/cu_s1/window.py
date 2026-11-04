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


def _fully_covered(x: int, y: int, w: int, h: int, monitors) -> bool:
    """Require every pixel of the client rectangle to lie on connected monitors."""
    if w <= 0 or h <= 0:
        return False
    right, bottom = x + w, y + h
    clipped = [(max(x, mx), max(y, my), min(right, mx + mw), min(bottom, my + mh))
               for mx, my, mw, mh in monitors if mw > 0 and mh > 0]
    clipped = [(a, b, c, d) for a, b, c, d in clipped if a < c and b < d]
    edges = sorted({x, right, *(v for a, _, c, _ in clipped for v in (a, c))})
    for left, edge in zip(edges, edges[1:]):
        intervals = sorted((b, d) for a, b, c, d in clipped if a <= left and c >= edge)
        end = y
        for start, stop in intervals:
            if start > end:
                break
            end = max(end, stop)
        if end < bottom:
            return False
    return bool(edges and clipped)


class WindowTarget:
    """Scope input to a captured root or one of its owned modal windows."""
    def __init__(self, hwnd: int | None = None):
        self.hwnd = hwnd or foreground()
        if not self.hwnd or not u.IsWindow(self.hwnd):
            raise ValueError('Target window is not available')
        self.root_pid = _process_id(self.hwnd)
        self.observed_hwnd = None
        self.observed_rect = None
        self.last_guard_failure = None

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
        self.last_guard_failure = None
        hwnd = self.observed_hwnd
        try:
            if hwnd is None or self.observed_rect is None:
                self.last_guard_failure = 'no observed capture'
            elif foreground() != hwnd:
                self.last_guard_failure = 'foreground changed'
            elif not self._in_scope(hwnd):
                self.last_guard_failure = 'target ownership or visibility changed'
            else:
                try:
                    if self._rect_for(hwnd) != self.observed_rect:
                        self.last_guard_failure = 'target geometry changed'
                except OSError:
                    self.last_guard_failure = 'target geometry unavailable'
        except OSError:
            self.last_guard_failure = 'target guard unavailable'
        return self.last_guard_failure is None

    def capture(self) -> Frame:
        hwnd = foreground()
        if not self._in_scope(hwnd):
            raise RuntimeError('Foreground window is outside the target scope or unavailable')
        x, y, w, h = self._rect_for(hwnd)
        full = capture(0)  # MSS monitor 0 covers the complete virtual desktop.
        bounds = (full.left, full.top, full.image.width, full.image.height)
        monitors = full.monitors if full.monitors is not None else (bounds,)
        if not _fully_covered(x, y, w, h, (bounds,)) or not _fully_covered(x, y, w, h, monitors):
            raise RuntimeError('Target must be fully visible on connected displays')
        if foreground() != hwnd or not self._in_scope(hwnd) or self._rect_for(hwnd) != (x, y, w, h):
            raise RuntimeError('Target changed during capture; reobserve before continuing')
        frame = Frame(full.image.crop((x - full.left, y - full.top, x - full.left + w, y - full.top + h)), x, y)
        self.observed_hwnd = hwnd
        self.observed_rect = (x, y, w, h)
        return frame
