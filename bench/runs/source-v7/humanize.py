"""Input layer: moves, clicks, typing, keys, scroll. mode="human" adds natural motion; "turbo" is instant."""
from __future__ import annotations

import ctypes
import math
import random
import sys
import time
from ctypes import wintypes

from . import screen  # noqa: F401  (ensures DPI awareness is set before any coordinates are used)

user32 = ctypes.windll.user32

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
MOUSEEVENTF_WHEEL = 0x0800
KEYEVENTF_EXTENDEDKEY, KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0001, 0x0002, 0x0004


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _U(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def _send(*inputs: INPUT) -> None:
    arr = (INPUT * len(inputs))(*inputs)
    if user32.SendInput(len(inputs), arr, ctypes.sizeof(INPUT)) != len(inputs):
        raise OSError("SendInput did not insert all input events")


def _mouse(flags: int, data: int = 0) -> INPUT:
    i = INPUT(type=INPUT_MOUSE)
    i.u.mi = MOUSEINPUT(0, 0, data & 0xFFFFFFFF, flags, 0, 0)
    return i


def _key(vk: int = 0, scan: int = 0, flags: int = 0) -> INPUT:
    i = INPUT(type=INPUT_KEYBOARD)
    i.u.ki = KEYBDINPUT(vk, scan, flags, 0, 0)
    return i


def cursor_pos() -> tuple[int, int]:
    p = wintypes.POINT()
    if not user32.GetCursorPos(ctypes.byref(p)):
        raise OSError("GetCursorPos failed")
    return p.x, p.y


def _min_jerk(t: float) -> float:
    return 10 * t**3 - 15 * t**4 + 6 * t**5


def _set_cursor_pos(x: int, y: int) -> None:
    if not user32.SetCursorPos(x, y):
        raise OSError("SetCursorPos failed")


def _check_guard(guard) -> None:
    if guard is not None and not guard():
        raise RuntimeError("input guard rejected action")


def move_to(x: int, y: int, mode: str = "human", rng: random.Random | None = None, *, guard=None) -> None:
    def guarded_move(tx: int, ty: int) -> None:
        _check_guard(guard)
        _set_cursor_pos(tx, ty)
    if mode == "turbo":
        guarded_move(x, y)
        return
    rng = rng or random
    sx, sy = cursor_pos()
    dist = math.hypot(x - sx, y - sy)
    if dist < 2:
        guarded_move(x, y)
        return
    # Fitts-style duration (target width ~40px), clamped
    dur = min(0.9, max(0.18, 0.1 + 0.12 * math.log2(dist / 40 + 1)))
    # Curved path: cubic Bezier with control points pushed off the straight line
    nx, ny = -(y - sy) / dist, (x - sx) / dist
    bend = rng.uniform(-0.18, 0.18) * dist
    c1 = (sx + (x - sx) * 0.3 + nx * bend, sy + (y - sy) * 0.3 + ny * bend)
    c2 = (sx + (x - sx) * 0.7 + nx * bend * 0.6, sy + (y - sy) * 0.7 + ny * bend * 0.6)

    def path(tx: float, ty: float, d: float, c1=c1, c2=c2, ox=sx, oy=sy) -> None:
        n = max(8, int(d / 0.008))
        t0 = time.perf_counter()
        for k in range(1, n + 1):
            u = _min_jerk(k / n)
            bx = (1 - u) ** 3 * ox + 3 * (1 - u) ** 2 * u * c1[0] + 3 * (1 - u) * u**2 * c2[0] + u**3 * tx
            by = (1 - u) ** 3 * oy + 3 * (1 - u) ** 2 * u * c1[1] + 3 * (1 - u) * u**2 * c2[1] + u**3 * ty
            guarded_move(round(bx), round(by))
            time.sleep(max(0.0, t0 + d * k / n - time.perf_counter()))

    if dist > 300 and rng.random() < 0.3:  # overshoot, then correct
        ang = math.atan2(y - sy, x - sx)
        ox_, oy_ = x + math.cos(ang) * rng.uniform(8, 22), y + math.sin(ang) * rng.uniform(8, 22)
        path(ox_, oy_, dur)
        sx2, sy2 = cursor_pos()
        mid = ((sx2 + x) / 2, (sy2 + y) / 2)
        path(x, y, 0.12, c1=mid, c2=mid, ox=sx2, oy=sy2)
    else:
        path(x, y, dur)
    guarded_move(x, y)


def click(x: int, y: int, button: str = "left", double: bool = False, mode: str = "human", *, guard=None) -> None:
    move_to(x, y, mode, guard=guard)
    if mode == "human":
        time.sleep(random.uniform(0.05, 0.14))
    down, up = (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP) if button == "right" else (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP)
    for _ in range(2 if double else 1):
        _check_guard(guard)
        try:
            _send(_mouse(down))
            if mode == "human":
                time.sleep(random.uniform(0.045, 0.11))
        finally:
            _send(_mouse(up))
        if double:
            time.sleep(0.06)


def scroll(x: int, y: int, dy: int, mode: str = "human", *, guard=None) -> None:
    move_to(x, y, mode, guard=guard)
    for _ in range(abs(dy)):
        _check_guard(guard)
        _send(_mouse(MOUSEEVENTF_WHEEL, (120 if dy > 0 else -120)))
        if mode == "human":
            time.sleep(random.uniform(0.03, 0.09))


def type_text(text: str, mode: str = "human", *, guard=None) -> None:
    for ch in text:
        if ch == "\n":
            press("enter", mode, guard=guard)
            continue
        encoded = ch.encode("utf-16-le")
        for offset in range(0, len(encoded), 2):
            unit = int.from_bytes(encoded[offset:offset + 2], "little")
            _check_guard(guard)
            try:
                _send(_key(0, unit, KEYEVENTF_UNICODE), _key(0, unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
            except OSError:
                # A partial SendInput batch could have inserted only the key-down.
                try:
                    _send(_key(0, unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
                except OSError:
                    pass
                raise
        if mode == "human":
            d = random.lognormvariate(math.log(0.07), 0.35)
            if ch in " ,.":
                d += random.uniform(0.03, 0.12)  # slight pause at word/phrase boundaries
            time.sleep(min(d, 0.4))


_VK = {"enter": 0x0D, "return": 0x0D, "tab": 0x09, "esc": 0x1B, "escape": 0x1B, "backspace": 0x08,
       "delete": 0x2E, "del": 0x2E, "space": 0x20, "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
       "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22, "ctrl": 0x11, "control": 0x11,
       "shift": 0x10, "alt": 0x12, "win": 0x5B, "windows": 0x5B}
_EXTENDED = {0x26, 0x28, 0x25, 0x27, 0x24, 0x23, 0x21, 0x22, 0x2E, 0x5B}


def _vk(name: str) -> int:
    n = name.strip().lower()
    if n in _VK:
        return _VK[n]
    if len(n) == 1 and n.isascii() and n.isalnum():
        return ord(n.upper())
    if n.startswith("f") and n[1:].isdigit() and 1 <= int(n[1:]) <= 24:
        return 0x70 + int(n[1:]) - 1
    raise ValueError(f"unknown key: {name}")


def press(combo: str, mode: str = "human", *, guard=None) -> None:
    vks = [_vk(k) for k in combo.split("+")]
    flag = lambda vk: KEYEVENTF_EXTENDEDKEY if vk in _EXTENDED else 0  # noqa: E731
    pressed = []
    try:
        for vk in vks:
            _check_guard(guard)
            pressed.append(vk)  # A failed SendInput may still have inserted part of a batch.
            _send(_key(vk, 0, flag(vk)))
            if mode == "human":
                time.sleep(random.uniform(0.02, 0.05))
    finally:
        pending_error = sys.exc_info()[0]
        release_error = None
        for vk in reversed(pressed):
            try:
                _send(_key(vk, 0, flag(vk) | KEYEVENTF_KEYUP))
            except OSError as exc:
                # Attempt every release even if an earlier release failed.
                release_error = exc
        if release_error is not None and pending_error is None:
            raise release_error
    if mode == "human":
        time.sleep(random.uniform(0.05, 0.12))
