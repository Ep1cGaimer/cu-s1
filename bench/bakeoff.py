"""Grounding bake-off: which light VLM clicks the right thing on unfamiliar surfaces, and how fast?

usage: python bench/bakeoff.py qwen3-vl:4b qwen3-vl:2b [--scale 1000]
Score = predicted click point lies inside the target bbox. Latency excludes the first (warm-up) call.
"""
from __future__ import annotations

import json
import statistics
import hashlib
import sys
import time
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from cu_s1.vlm import Vlm, ACTION_PROMPT  # noqa: E402

CASES = Path(__file__).parent / "cases"


def run(model: str, scale: float, verbose: bool, url: str | None = None, *, out: Path | None = None,
        max_side: int = 1280, limit: int | None = None, manifest: Path | None = None) -> dict:
    vlm = Vlm(model, coord_scale=scale, base_url=url, timeout=90)
    cases = json.loads((manifest or CASES / "cases.json").read_text(encoding="utf-8"))[:limit]
    warm_start = time.perf_counter()
    vlm.decide("Click anything.", Image.open(CASES / cases[0]["image"]).convert("RGB"))  # warm-up / load
    warmup_ms = (time.perf_counter() - warm_start) * 1000
    by_kind: dict[str, list[int]] = {}
    lat: list[float] = []
    bad = 0
    predictions = []
    for c in cases:
        img = Image.open(CASES / c["image"]).convert("RGB")
        s = min(1.0, max_side / max(img.size))
        sent = img if s == 1.0 else img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
        try:
            a = vlm.decide(c["instruction"], sent)
        except Exception as exc:
            from cu_s1.vlm import Action
            a = Action("invalid", raw=f"{type(exc).__name__}: {exc}")
        lat.append(a.latency_ms)
        hit = 0
        if c.get("absent"):
            hit = int(a.kind == "handback")
        elif a.kind in ("click", "double_click", "right_click") and a.nx is not None:
            px, py = a.nx * img.width, a.ny * img.height
            x0, y0, x1, y1 = c["bbox"]
            hit = int(x0 <= px < x1 and y0 <= py < y1)
        else:
            bad += 1
        by_kind.setdefault(c["kind"], []).append(hit)
        predictions.append({"id":c["id"], "kind":c["kind"], "instruction":c["instruction"],
                            "hit":bool(hit), "action":a.kind,"nx":a.nx,"ny":a.ny,
                            "raw":a.raw,"latency_ms":a.latency_ms})
        if out:
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps({"model":model,"max_side":max_side,"cases":predictions},indent=2),encoding="utf-8")
        if verbose:
            print(f"  {c['id']} hit={hit} {a.latency_ms:6.0f}ms  {c['instruction']!a} -> {a.raw.strip()[:90]!a}", flush=True)
    allhits = [h for v in by_kind.values() for h in v]
    result = {
        "model": model,
        "hit_rate": sum(allhits) / len(allhits),
        "by_kind": {k: sum(v) / len(v) for k, v in by_kind.items()},
        "unparsable_or_non_click": bad,
        "median_ms": statistics.median(lat),
        "p90_ms": sorted(lat)[__import__('math').ceil(0.9 * len(lat)) - 1],
        "max_side": max_side, "count": len(cases), "cases": predictions,
        "structured_output":vlm.structured,"prompt_sha256":hashlib.sha256(ACTION_PROMPT.encode()).hexdigest(),
        "warmup_ms_excluded":warmup_ms,
        "client_source_sha256":hashlib.sha256((CASES.parent.parent/'src/cu_s1/vlm.py').read_bytes()).hexdigest(),
    }
    if out:
        out.write_text(json.dumps(result,indent=2),encoding="utf-8")
    return result


if __name__ == "__main__":
    argv = sys.argv[1:]
    opts: dict[str, str] = {}
    for flag in ("--scale", "--url", "--out", "--max-side", "--limit", "--manifest"):
        if flag in argv:
            i = argv.index(flag)
            opts[flag] = argv[i + 1]
            del argv[i : i + 2]
    verbose = "--verbose" in argv
    args = [a for a in argv if not a.startswith("--")]
    scale = float(opts.get("--scale", 1000))
    rows = []
    for m in args:
        print(f"== {m}")
        rows.append(run(m, scale, verbose, opts.get("--url"),
                        out=Path(opts["--out"]) if "--out" in opts else None,
                        max_side=int(opts.get("--max-side",1280)),
                        limit=int(opts["--limit"]) if "--limit" in opts else None,
                        manifest=Path(opts["--manifest"]) if "--manifest" in opts else None))
    print("\nmodel | hit | icon | text | real-app | bad | median ms | p90 ms")
    for r in rows:
        k = r["by_kind"]
        print(f"{r['model']} | {r['hit_rate']:.0%} | {k.get('unfamiliar-icon', 0):.0%} | "
              f"{k.get('unfamiliar-text', 0):.0%} | {k.get('real-app', 0):.0%} | {r['unparsable_or_non_click']} | "
              f"{r['median_ms']:.0f} | {r['p90_ms']:.0f}")
