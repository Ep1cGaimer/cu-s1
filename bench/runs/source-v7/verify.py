"""Did the action do what we expected? Cheap pixel-diff gate first, optional VLM yes/no second."""
from __future__ import annotations

import time

import numpy as np
from PIL import Image

from .screen import Frame, capture


def _small(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("L").resize((320, 200)), dtype=np.int16)


def changed_fraction(a: Image.Image, b: Image.Image, thresh: int = 12) -> float:
    return float((np.abs(_small(a) - _small(b)) > thresh).mean())


def has_visible_change(a: Image.Image, b: Image.Image) -> bool:
    """Detect small controls too. A change is evidence of input, not task success."""
    if a.size != b.size:
        return True
    if changed_fraction(a, b) >= 0.0002:
        return True
    # Thumbnail averaging can erase a check mark or a thin focus outline.
    delta = np.abs(np.asarray(a.convert("RGB"), dtype=np.int16) -
                   np.asarray(b.convert("RGB"), dtype=np.int16))
    return bool(np.count_nonzero(delta.max(axis=2) > 24) >= 8)


def wait_stable(prev: Frame, max_s: float = 1.5, poll_s: float = 0.08, capture_fn=None) -> Frame:
    """Return the first frame after which the screen stops changing (animations/loading settle)."""
    t0 = time.perf_counter()
    last = prev
    saw_change = False
    while time.perf_counter() - t0 < max_s:
        time.sleep(poll_s)
        cur = (capture_fn or capture)()
        if has_visible_change(last.image, cur.image):
            saw_change = True
        elif saw_change or time.perf_counter() - t0 > 0.25:
            return cur
        last = cur
    return last
