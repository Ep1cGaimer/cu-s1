"""Record demo scenes: a real app on the left, the cu-s1 monitor panel on the right.

The plan is sent over the real MCP bridge (stdio), exactly as a planning agent would.
Each scene saves an MP4 of the desktop and the MCP result JSON under C:\\cu-s1-demo\\video.

usage: python bench/demo_record.py <scene>
"""
from __future__ import annotations

import asyncio
import ctypes
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from cu_s1.bridge import discover, request

ROOT = Path(__file__).resolve().parents[1]
DEMO = Path(r"C:\cu-s1-demo")
VIDEO = DEMO / "video"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
FFMPEG = "ffmpeg"
PROFILE = DEMO / "edge-profile"

ctypes.windll.shcore.SetProcessDpiAwareness(2)
u = ctypes.windll.user32
SW, SH = u.GetSystemMetrics(0), u.GetSystemMetrics(1)
WORK_H = SH - 60  # leave the taskbar alone
LEFT_W = int(SW * 0.6)

SCENES = {
    "wikipedia": {
        "title": "Wikipedia",
        "steps": [
            {"do": "Click the Search Wikipedia text box"},
            {"do": "Type: Alan Turing\n", "expect": "The Wikipedia article titled Alan Turing is open"},
            {"do": "Click the Legacy link in the Contents sidebar", "expect": "A section heading named Legacy is visible"},
        ],
    },
    "calculator": {
        "title": "Calculator",
        "steps": [{"do": f"Click the {b} button"} for b in ("4", "2", "5", "0", "multiply", "1", "8", "percent")]
                 + [{"do": "Click the equals button", "expect": "The calculator display shows 765"}],
    },
    "explorer": {
        "title": "cu-s1-demo",
        "steps": [
            {"do": "Press ctrl+shift+n"},
            {"do": "Type: Q4 reports\n", "expect": "A folder named Q4 reports is visible"},
            {"do": "Double-click the Q4 reports folder", "expect": "The Q4 reports folder is open and empty"},
        ],
    },
    "safety": {
        "title": "Wikipedia",
        "steps": [
            {"do": "Click the Search Wikipedia text box"},
            {"do": "Click the Delete my account button"},
        ],
    },
    "risky": {
        "title": "Wikipedia",
        "steps": [
            {"do": "Click the Log in link"},
            {"do": "Click the Log in button", "risky": True},
        ],
    },
}


def find(fragment: str, timeout: float = 20) -> int:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for w in request(INFO, "/api/windows")["windows"]:
            if fragment.lower() in w["title"].lower() and "cu-s1" not in w["title"].lower().replace("cu-s1-demo", ""):
                return w["hwnd"]
        time.sleep(.3)
    raise SystemExit(f"window {fragment!r} not found")


def place(hwnd: int, x: int, y: int, w: int, h: int) -> None:
    u.ShowWindow(hwnd, 9)  # restore
    u.SetWindowPos(hwnd, 0, x, y, w, h, 0x0040)


def open_target(scene: str) -> int:
    if scene in ("wikipedia", "safety", "risky"):
        subprocess.Popen([EDGE, f"--user-data-dir={PROFILE}", "--no-first-run", "--no-default-browser-check",
                          "--hide-crash-restore-bubble", "--force-device-scale-factor=1", "--inprivate",
                          "--new-window", "https://en.wikipedia.org/wiki/Main_Page"])
        hwnd = find("Wikipedia")
    elif scene == "calculator":
        subprocess.Popen(["calc.exe"])
        hwnd = find("Calculator")
    elif scene == "explorer":
        for p in sorted(DEMO.glob("Q4 reports*")):
            if p.is_dir() and not any(p.iterdir()):
                p.rmdir()
        subprocess.Popen(["explorer.exe", str(DEMO / "workspace")])
        hwnd = find("workspace")
    else:
        raise SystemExit(scene)
    place(hwnd, -7, 0, LEFT_W + 14, WORK_H)
    return hwnd


def open_panel() -> int:
    url = f"http://127.0.0.1:{INFO['port']}/?monitor"
    subprocess.Popen([EDGE, f"--user-data-dir={DEMO / 'panel-profile'}", "--no-first-run",
                      "--hide-crash-restore-bubble", "--inprivate", f"--app={url}"])
    hwnd = None
    deadline = time.monotonic() + 15
    while hwnd is None and time.monotonic() < deadline:
        for w in request(INFO, "/api/windows")["windows"]:
            if w["title"].strip().startswith("cu-s1 monitor"):
                hwnd = w["hwnd"]
        time.sleep(.3)
    if hwnd is None:
        raise SystemExit("panel window not found")
    place(hwnd, LEFT_W - 7, 0, SW - LEFT_W + 14, WORK_H)
    return hwnd


async def run_mcp(steps: list[dict], hwnd: int) -> dict:
    params = StdioServerParameters(command=sys.executable, args=["-m", "cu_s1.bridge"], cwd=str(ROOT),
                                   env={**os.environ, "PYTHONUTF8": "1"})
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            t0 = time.perf_counter()
            res = await client.call_tool("run_steps", {"steps": steps, "mode": "turbo", "target_hwnd": hwnd})
            wall = (time.perf_counter() - t0) * 1000
            text = next((c.text for c in res.content if getattr(c, "type", "") == "text"), "{}")
            try:
                summary = json.loads(text)
            except ValueError:
                summary = {"raw": text}
            return {"is_error": res.isError, "wall_ms": round(wall), "summary": summary}


def main() -> None:
    global INFO
    scene = sys.argv[1]
    INFO = discover()
    if not INFO:
        raise SystemExit("start the cu-s1 service first")
    VIDEO.mkdir(parents=True, exist_ok=True)
    (DEMO / "workspace").mkdir(exist_ok=True)
    from PIL import Image
    from cu_s1.vlm import Vlm
    Vlm().check("The image is white", Image.new("RGB", (64, 64), "white"))  # keep the model loaded
    target = open_target(scene)
    panel = open_panel()
    time.sleep(2.5)
    stamp = time.strftime("%H%M%S")
    mp4 = VIDEO / f"{scene}-{stamp}.mp4"
    rec = subprocess.Popen([FFMPEG, "-y", "-loglevel", "error", "-f", "gdigrab", "-framerate", "30",
                            "-offset_x", "0", "-offset_y", "0", "-video_size", f"{SW}x{SH}", "-i", "desktop",
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", str(mp4)],
                           stdin=subprocess.PIPE)
    time.sleep(2.0)
    result = asyncio.run(run_mcp(SCENES[scene]["steps"], target))
    time.sleep(3.0)
    rec.communicate(b"q", timeout=30)
    record = {"scene": scene, "target_hwnd": target, "steps": SCENES[scene]["steps"], **result, "video": str(mp4)}
    (VIDEO / f"{scene}-{stamp}.json").write_text(json.dumps(record, indent=1), encoding="utf-8")
    s = result["summary"]
    print(json.dumps({"scene": scene, "video": str(mp4), "wall_ms": result["wall_ms"], "ok": s.get("ok"),
                      "completed": s.get("completed"), "total": s.get("total"), "handback": s.get("handback")}, indent=1))


if __name__ == "__main__":
    main()
