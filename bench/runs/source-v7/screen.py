"""Screen capture and coordinate mapping (Windows, DPI-aware)."""
from __future__ import annotations

import base64
import ctypes
import io
import math
import os
from dataclasses import dataclass

import mss
from PIL import Image


def set_dpi_aware() -> None:
    """Without this, captures and SendInput coordinates disagree at 125-150% scaling."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


set_dpi_aware()


@dataclass
class Frame:
    image: Image.Image  # full-resolution capture
    left: int  # monitor origin in virtual-desktop pixels
    top: int

    @property
    def size(self) -> tuple[int, int]:
        return self.image.size

    def to_screen(self, nx: float, ny: float) -> tuple[int, int]:
        """Normalized (0..1) frame coords -> absolute screen pixels."""
        w, h = self.image.size
        if not (math.isfinite(nx) and math.isfinite(ny) and 0 <= nx <= 1 and 0 <= ny <= 1 and w and h):
            raise ValueError("coordinates must be within the frame")
        return self.left + round(nx * (w - 1)), self.top + round(ny * (h - 1))

    def downscaled(self, max_side: int | None = None) -> Image.Image:
        if max_side is None:
            raw = os.environ.get("CU_S1_MAX_SIDE", "1280")
            try:
                max_side = int(raw)
            except (ValueError, TypeError):
                raise ValueError("CU_S1_MAX_SIDE must be an integer from 320 to 1920") from None
        if type(max_side) is not int or not 320 <= max_side <= 1920:
            raise ValueError("max_side must be an integer from 320 to 1920")
        w, h = self.image.size
        s = min(1.0, max_side / max(w, h))
        if s == 1.0:
            return self.image
        return self.image.resize((round(w * s), round(h * s)), Image.LANCZOS)


def capture(monitor: int = 1) -> Frame:
    with mss.mss() as sct:
        mon = sct.monitors[monitor]
        shot = sct.grab(mon)
        img = Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")
    return Frame(img, mon["left"], mon["top"])


def to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def to_b64_png(img: Image.Image) -> str:
    return base64.b64encode(to_png_bytes(img)).decode()
