"""Real-app grounding cases. Launch an app, screenshot it, label buttons from its UIA tree (answer key only), close it.

usage: python bench/gen_real_cases.py [per_app]
Appends kind="real-app" cases to bench/cases/cases.json (keeps the generated 'unfamiliar-*' ones).
No input is sent to any existing window; we only start the apps listed below and close those windows.
Images may show whatever is on screen, so bench/cases/real_*.png should not be shared.
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from cu_s1.screen import capture  # noqa: E402  (sets DPI awareness BEFORE uiautomation loads)

import uiautomation as auto  # noqa: E402

CASES = Path(__file__).parent / "cases"
# (launch command, window title substring, label)
APPS = [("calc.exe", "Calculator", "calculator"), ("explorer.exe ms-settings:", "Settings", "settings"),
        ("notepad.exe", "Notepad", "notepad")]
KINDS = {"ButtonControl", "ListItemControl", "TabItemControl", "MenuItemControl", "CheckBoxControl"}


def walk(ctrl, depth=0, max_depth=14, out=None):
    out = [] if out is None else out
    if depth > max_depth:
        return out
    try:
        for c in ctrl.GetChildren():
            out.append(c)
            walk(c, depth + 1, max_depth, out)
    except Exception:
        pass
    return out


def find_window(sub: str, timeout: float = 15.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        for w in auto.GetRootControl().GetChildren():
            if sub.lower() in (w.Name or "").lower() and w.ControlTypeName == "WindowControl" and not w.IsOffscreen:
                return w
        time.sleep(0.5)
    return None


def main(per_app: int) -> None:
    rng = random.Random(7)
    cases = []
    for cmd, sub, label in APPS:
        subprocess.Popen(cmd, shell=True)
        win = find_window(sub)
        if win is None:
            print(f"! {label}: window not found, skipping")
            continue
        time.sleep(2.0)  # let it render
        frame = capture()
        W, H = frame.image.size
        img_name = f"real_{label}.png"
        frame.image.save(CASES / img_name)
        els = [c for c in walk(win) if c.ControlTypeName in KINDS]
        names = Counter((c.Name or "").strip() for c in els)
        cand = []
        for c in els:
            n = (c.Name or "").strip()
            if not n or names[n] != 1 or len(n) > 40 or c.IsOffscreen:
                continue
            r = c.BoundingRectangle
            x0, y0, x1, y1 = r.left - frame.left, r.top - frame.top, r.right - frame.left, r.bottom - frame.top
            if x1 - x0 < 14 or y1 - y0 < 14 or x0 < 0 or y0 < 0 or x1 > W or y1 > H:
                continue
            noun = "button" if c.ControlTypeName == "ButtonControl" else "item"
            cand.append({"image": img_name, "instruction": f"Click '{n}' ({label}, {noun}).",
                         "bbox": [x0, y0, x1, y1], "kind": "real-app"})
        rng.shuffle(cand)
        picked = cand[:per_app]
        cases += picked
        print(f"{label}: {len(els)} controls, {len(cand)} usable, kept {len(picked)} (screen {W}x{H})")
        try:
            win.GetWindowPattern().Close()
        except Exception as e:  # noqa: BLE001
            print(f"  (could not close {label} window: {e})")
        time.sleep(1.5)
    for i, c in enumerate(cases):
        c["id"] = f"real{i:02d}"
    existing = [c for c in json.loads((CASES / "cases.json").read_text()) if not c["kind"].startswith("real")]
    (CASES / "cases.json").write_text(json.dumps(existing + cases, indent=1), encoding="utf-8")
    print(f"added {len(cases)} real-app cases")
    for c in cases[:6]:
        print("  ", c["instruction"], c["bbox"])


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8)
