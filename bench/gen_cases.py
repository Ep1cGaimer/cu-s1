"""Generate unfamiliar-surface grounding cases: odd pages with known element boxes.

Each case: PNG screenshot (1280x800) + a target bbox + an instruction. Elements are icon-only
buttons or chrome-less text in randomized styles, so no model has seen these exact surfaces.
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
from pathlib import Path

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
W, H = 1280, 800
OUT = Path(__file__).parent / "cases"

ICONS = {
    "trash can / delete": "🗑",
    "gear / settings": "⚙",
    "magnifying glass / search": "🔍",
    "envelope / mail": "✉",
    "house / home": "🏠",
    "star / favorite": "⭐",
    "printer": "🖨",
    "floppy disk / save": "💾",
    "refresh / reload": "🔄",
    "plus / add": "➕",
    "camera": "📷",
    "bell / notifications": "🔔",
    "lock": "🔒",
    "folder": "📁",
    "pencil / edit": "✏",
}
WORDS = ["Submit", "Cancel", "Continue", "Dismiss", "Export", "Archive", "Share", "Confirm", "Retry"]
BGS = ["#0f172a", "#fef3c7", "#e0f2fe", "#1f2937", "linear-gradient(135deg,#f472b6,#60a5fa)", "#d1fae5", "#111", "#fde68a"]
SHAPES = ["50%", "12px", "999px", "2px", "0"]
PALETTE = ["#ef4444", "#22c55e", "#3b82f6", "#a855f7", "#f59e0b", "#14b8a6", "#e11d48", "#64748b"]


def place(rng: random.Random, n: int, size_range=(48, 84)) -> list[tuple[int, int, int, int]]:
    boxes: list[tuple[int, int, int, int]] = []
    tries = 0
    while len(boxes) < n and tries < 2000:
        tries += 1
        s = rng.randint(*size_range)
        x, y = rng.randint(30, W - s - 30), rng.randint(30, H - s - 30)
        if all(x + s + 24 < bx or bx + bw + 24 < x or y + s + 24 < by or by + bh + 24 < y for bx, by, bw, bh in boxes):
            boxes.append((x, y, s, s))
    return boxes


def make_case(i: int) -> dict:
    rng = random.Random(1000 + i)
    icon_mode = i % 5 != 4  # ~80% icon, 20% chrome-less text
    bg = rng.choice(BGS)
    dark = bg in ("#0f172a", "#1f2937", "#111")
    els, target = [], None
    if icon_mode:
        names = rng.sample(list(ICONS), 8)
        boxes = place(rng, len(names))
        for name, (x, y, w, h) in zip(names, boxes):
            shape, col = rng.choice(SHAPES), rng.choice(PALETTE)
            filled = rng.random() < 0.6
            style = (
                f"left:{x}px;top:{y}px;width:{w}px;height:{h}px;border-radius:{shape};"
                f"font-size:{int(w*0.55)}px;"
                + (f"background:{col};" if filled else f"border:3px solid {col};background:transparent;")
            )
            els.append((style, ICONS[name], (x, y, w, h), name))
        t = rng.choice(els)
        instruction = f"Click the {t[3]} icon."
        target = t[2]
    else:
        names = rng.sample(WORDS, 6)
        boxes = place(rng, len(names), (90, 130))
        for name, (x, y, w, h) in zip(names, boxes):
            h = 34
            col = rng.choice(PALETTE)
            fam = rng.choice(["Georgia", "Impact", "Courier New", "Segoe Script", "Trebuchet MS"])
            style = f"left:{x}px;top:{y}px;width:{w}px;height:{h}px;color:{col};font:700 20px '{fam}';"
            els.append((style, name, (x, y, w, h), name))
        t = rng.choice(els)
        instruction = f"Click '{t[3]}'."
        target = t[2]
    fg = "#f8fafc" if dark else "#0f172a"
    items = "\n".join(f'<div class="e" style="{s}">{label}</div>' for s, label, _, _ in els)
    html = f"""<!doctype html><meta charset=utf-8><style>
html,body{{margin:0;width:{W}px;height:{H}px;overflow:hidden;background:{bg};color:{fg};}}
.e{{position:absolute;display:flex;align-items:center;justify-content:center;box-sizing:border-box;
font-family:'Segoe UI Emoji','Segoe UI',sans-serif;}}
</style><body>{items}</body>"""
    OUT.mkdir(exist_ok=True)
    html_path = OUT / f"case{i:02d}.html"
    html_path.write_text(html, encoding="utf-8")
    png_path = OUT / f"case{i:02d}.png"
    subprocess.run(
        [EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
         f"--window-size={W},{H}", f"--screenshot={png_path}", html_path.as_uri()],
        check=True, capture_output=True, timeout=60,
    )
    x, y, w, h = target
    return {"id": f"case{i:02d}", "image": png_path.name, "instruction": instruction, "bbox": [x, y, x + w, y + h],
            "kind": "unfamiliar-icon" if icon_mode else "unfamiliar-text"}


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    cases = [make_case(i) for i in range(n)]
    (OUT / "cases.json").write_text(json.dumps(cases, indent=1), encoding="utf-8")
    print(f"wrote {len(cases)} cases to {OUT}")
