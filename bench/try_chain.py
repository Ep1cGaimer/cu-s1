"""Run one chain end-to-end on the real desktop: python bench/try_chain.py [human|turbo] [model]"""
import json
import sys
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from cu_s1.runner import Step, run_steps  # noqa: E402
from cu_s1.screen import to_png_bytes  # noqa: E402
from cu_s1.vlm import Vlm  # noqa: E402

mode = sys.argv[1] if len(sys.argv) > 1 else "human"
model = sys.argv[2] if len(sys.argv) > 2 else "qwen3-vl:2b-instruct"
chain = [
    Step("Press the Windows key", "the Start menu is open"),
    Step("Type: notepad"),
    Step("Press Enter", "a Notepad window is open"),
    Step("Click inside the Notepad text area"),
    Step("Type: hello from system 1", "the text 'hello from system 1' is visible in Notepad"),
]
r = run_steps(chain, Vlm(model), mode)
print(json.dumps({"ok": r.ok, "completed": r.completed, "total": r.total, "handback": r.handback,
                  "total_ms": round(r.total_ms), "steps": [asdict(s) for s in r.steps]}, indent=1))
if r.final_frame:
    out = Path(__file__).parent / "last_frame.png"
    out.write_bytes(to_png_bytes(r.final_frame.downscaled(1280)))
    print("final frame ->", out)

