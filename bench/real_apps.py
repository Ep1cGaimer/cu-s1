"""Real-application runs for the demo: Notepad, Calculator, File Explorer, browser.

Everything is created under C:\\cu-s1-demo. Each run binds the chain to one window
handle, activates it, executes through the same MCP tool the bridge exposes and
saves the summary plus the final view under bench/runs/real-apps/.

usage: python bench/real_apps.py <task> [--hwnd N]
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import subprocess
import sys
import time
from pathlib import Path

from cu_s1 import app, server

DEMO = Path(r"C:\cu-s1-demo")
OUT = Path(__file__).with_name("runs") / "real-apps"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

TASKS = {
    "notepad": [
        {"do": "Click inside the large empty text editing area of Notepad"},
        {"do": "Type: Standup 5 Nov - cu-s1 demo\nShip the hackathon build\nRecord the comparison video\n"},
        {"do": "Press ctrl+s", "expect": "The Notepad tab title shows note.txt"},
    ],
    "wikipedia": [
        {"do": "Click the Search Wikipedia text box"},
        {"do": "Type: Alan Turing\n", "expect": "The Wikipedia article titled Alan Turing is open"},
        {"do": "Click the Legacy link in the Contents sidebar", "expect": "A section heading named Legacy is visible"},
    ],
    "explorer": [
        {"do": "Press ctrl+shift+n"},
        {"do": "Type: reports\n", "expect": "A folder named reports is visible"},
    ],
    "calculator_visual": [
        {"do": "Click the 4 button"}, {"do": "Click the 2 button"}, {"do": "Click the 5 button"},
        {"do": "Click the 0 button"}, {"do": "Click the multiply button"},
        {"do": "Click the 1 button"}, {"do": "Click the 8 button"}, {"do": "Click the percent button"},
        {"do": "Click the equals button", "expect": "The calculator display shows 765"},
    ],
    "calculator": [
        {"do": "Type: 4250*18%="},
        {"do": "Press ctrl+c", "expect": "The calculator display shows 765"},
    ],
}


def find_window(fragment: str, timeout: float = 8.0) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for w in server.windows():
            if fragment.lower() in w["title"].lower():
                return w["hwnd"]
        time.sleep(.25)
    raise SystemExit(f"no window containing {fragment!r}")


async def run(task: str, hwnd: int, steps: list[dict]) -> dict:
    app.activate_target(hwnd)
    t0 = time.perf_counter()
    result = await server.run_steps_tool([server.StepInput.model_validate(s) for s in steps], "turbo", hwnd)
    wall = (time.perf_counter() - t0) * 1000
    packed = app.pack_result(result)
    OUT.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    if packed["screenshot"]:
        (OUT / f"{task}-{stamp}.png").write_bytes(base64.b64decode(packed["screenshot"].split(",", 1)[1]))
    record = {"task": task, "hwnd": hwnd, "steps": steps, "wall_ms": round(wall), "summary": packed["summary"]}
    (OUT / f"{task}-{stamp}.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    return record


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("task", choices=sorted(TASKS))
    p.add_argument("--hwnd", type=int)
    a = p.parse_args()
    DEMO.mkdir(exist_ok=True)
    hwnd = a.hwnd
    if hwnd is None and a.task == "notepad":
        note = DEMO / "note.txt"
        note.write_text("", encoding="utf-8")
        subprocess.Popen(["notepad.exe", str(note)])
        hwnd = find_window("note.txt")
    elif hwnd is None and a.task.startswith("calculator"):
        subprocess.Popen(["calc.exe"])
        hwnd = find_window("Calculator")
    elif hwnd is None and a.task == "wikipedia":
        # Throwaway profile: no user cookies, history or sign-ins.
        subprocess.Popen([EDGE, f"--user-data-dir={DEMO / 'edge-profile'}", "--no-first-run",
                          "--no-default-browser-check", "--new-window", "--window-size=1180,740",
                          "--window-position=30,30", "https://en.wikipedia.org/wiki/Main_Page"])
        hwnd = find_window("Wikipedia", timeout=20)
        time.sleep(2.0)
    elif hwnd is None and a.task == "explorer":
        subprocess.Popen(["explorer.exe", str(DEMO)])
        hwnd = find_window("cu-s1-demo", timeout=10)
    time.sleep(1.0)
    rec = asyncio.run(run(a.task, hwnd, TASKS[a.task]))
    s = rec["summary"]
    print(json.dumps({"ok": s["ok"], "completed": s["completed"], "total": s["total"],
                      "wall_ms": rec["wall_ms"], "handback": s["handback"],
                      "steps": [(x["status"], x["action"], round(x["decide_ms"]), x["note"]) for x in s["steps"]]}, indent=1))


if __name__ == "__main__":
    sys.exit(main())
