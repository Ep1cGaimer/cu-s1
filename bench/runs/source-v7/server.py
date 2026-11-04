"""MCP server: a big agent hands over a chain of instructions; a light local VLM executes them."""
from __future__ import annotations

import asyncio
import json
import threading
import os
from functools import partial
from dataclasses import asdict

from mcp.server.fastmcp import FastMCP, Image
from pydantic import BaseModel, Field, StrictBool

from .runner import Step, run_steps
from .screen import capture, to_png_bytes
from .vlm import Vlm
from .window import WindowTarget, list_windows
from .verify import wait_stable

mcp = FastMCP("cu-s1")
_vlm = Vlm(coord_scale=float(os.environ.get("CU_S1_SCALE", "1000")))

# Protected across the event-loop and worker threads. A cancelled caller does not
# clear the active slot; only the worker that owns it can do so.
_chain_lock = threading.Lock()
_active_stop: threading.Event | None = None
_workers: set[asyncio.Task] = set()


def _begin_chain() -> threading.Event:
    global _active_stop
    with _chain_lock:
        if _active_stop is not None:
            raise RuntimeError("another execution chain is still running")
        _active_stop = threading.Event()
        return _active_stop


def _finish_chain(event: threading.Event) -> None:
    global _active_stop
    with _chain_lock:
        if _active_stop is event:
            _active_stop = None


@mcp.tool(name="stop")
def stop_tool() -> dict:
    """Request cooperative stop of the active chain; a running model call may finish first."""
    with _chain_lock:
        event = _active_stop
        if event is not None:
            event.set()
        return {"active": event is not None, "stop_requested": event is not None}


class StepInput(BaseModel):
    do: str = Field(min_length=1, max_length=100000)
    expect: str | None = None
    risky: StrictBool = False
    confirmed: StrictBool = False


@mcp.tool(name="run_steps")
async def run_steps_tool(steps: list[StepInput], mode: str = "turbo", target_hwnd: int | None = None) -> list:
    """Execute a chain of UI instructions on this computer using a fast local vision model.

    Use this instead of looking at the screen and clicking one step at a time: send the whole chain.
    Each step is {"do": "natural-language instruction for ONE action", "expect": "optional: what should be
    visible on screen afterwards", "risky": optional bool, "confirmed": optional bool}. Example:
      [{"do": "Click the Note field"}, {"do": "Type: cedar-47"},
       {"do": "Click Apply", "expect": "The status says COMPLETE"}]
    Pixels in, mouse/keyboard out: no app APIs. Execution stops at the first step that does not do what
    was expected and returns a screenshot so you can re-plan. Steps with risky=true (send, delete, pay) are
    refused until you resend them with confirmed=true. mode: "human" (natural cursor/typing) or "turbo".
    Activate the target first; use a hwnd returned by windows() to bind the chain to it.
    By default the current foreground window is bound. Same-process owned dialogs may be recaptured;
    unexpected focus or geometry changes stop execution. A newly opened dialog is observed before input.
    Each click receives an additional visual target-presence check. Supply expect to verify outcomes;
    a pixel change alone is not proof that the requested task succeeded.
    """
    chain = [Step(do=s.do, expect=s.expect, risky=s.risky, confirmed=s.confirmed)
             for s in steps]
    if len(chain)>64:
        raise ValueError("Send at most 64 steps per chain")
    event = _begin_chain()

    def worker() -> list:
        try:
            if event.is_set():
                raise RuntimeError("execution stopped")
            target = WindowTarget(target_hwnd)

            def guarded_capture():
                if event.is_set():
                    raise RuntimeError("execution stopped before capture")
                return target.capture()

            def guarded_input():
                return not event.is_set() and target.guard()

            r = run_steps(chain, _vlm, mode if mode in ("human", "turbo") else "turbo",
                          capture_fn=guarded_capture, input_guard=guarded_input,
                          stable_fn=partial(wait_stable, capture_fn=guarded_capture))
            summary = {
                "ok": r.ok, "completed": r.completed, "total": r.total, "handback": r.handback,
                "total_ms": round(r.total_ms), "steps": [asdict(s) for s in r.steps],
            }
            out: list = [json.dumps(summary, indent=1)]
            if r.final_frame is not None:
                out.append(Image(data=to_png_bytes(r.final_frame.downscaled(1024)), format="png"))
            return out
        finally:
            _finish_chain(event)

    try:
        task = asyncio.create_task(asyncio.to_thread(worker))
        _workers.add(task)
    except BaseException:
        _finish_chain(event)
        raise

    def consume_exception(done: asyncio.Task) -> None:
        _workers.discard(done)
        if not done.cancelled():
            done.exception()

    task.add_done_callback(consume_exception)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        event.set()
        raise

@mcp.tool()
def windows() -> list[dict]:
    """List visible window titles and handles for target binding; no UI accessibility selectors."""
    return list_windows()


@mcp.tool()
def look(target_hwnd: int | None = None) -> Image:
    """Take a screenshot of the primary display (downscaled)."""
    frame = WindowTarget(target_hwnd).capture() if target_hwnd is not None else capture()
    return Image(data=to_png_bytes(frame.downscaled(1024)), format="png")


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
