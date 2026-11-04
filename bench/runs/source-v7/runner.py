"""Executes a chain of instructions with the system 1 model; hands back on surprise."""
from __future__ import annotations

import time
import re
from dataclasses import dataclass, field

from . import humanize
from .screen import Frame, capture
from .verify import has_visible_change, wait_stable
from .vlm import Action, Vlm, validate_action, requested_action_kind

MUTATING = {"click", "double_click", "right_click", "type", "key", "scroll"}


@dataclass
class Step:
    do: str
    expect: str | None = None
    risky: bool = False
    confirmed: bool = False


@dataclass
class StepResult:
    i: int
    do: str
    status: str  # ok | no_change | expect_failed | invalid_action | needs_confirmation | error
    action: str = ""
    decide_ms: float = 0.0
    act_ms: float = 0.0
    verify_ms: float = 0.0
    attempts: int = 1
    note: str = ""
    verified: bool = False
    check_reply: str = ""
    active_region: tuple[float, float, float, float] | None = None


@dataclass
class ChainResult:
    ok: bool
    completed: int
    total: int
    steps: list[StepResult] = field(default_factory=list)
    handback: str | None = None
    final_frame: Frame | None = None
    total_ms: float = 0.0


def _describe(a: Action) -> str:
    if a.kind in ("click", "double_click", "right_click") and a.nx is not None:
        return f"{a.kind}({a.nx:.3f},{a.ny:.3f})"
    if a.kind == "type":
        return f"type({a.text!r})"
    if a.kind == "key":
        return f"key({a.keys})"
    if a.kind == "scroll":
        return f"scroll({a.dy})"
    return a.kind


def _execute(a: Action, frame: Frame, mode: str, input_guard=None) -> None:
    if a.kind in ("click", "double_click", "right_click"):
        x, y = frame.to_screen(a.nx, a.ny)
        humanize.click(x, y, "right" if a.kind == "right_click" else "left", a.kind == "double_click", mode, guard=input_guard)
    elif a.kind == "type":
        humanize.type_text(a.text or "", mode, guard=input_guard)
    elif a.kind == "key":
        humanize.press(a.keys or "", mode, guard=input_guard)
    elif a.kind == "scroll":
        x, y = frame.to_screen(a.nx if a.nx is not None else 0.5, a.ny if a.ny is not None else 0.5)
        humanize.scroll(x, y, a.dy or -3, mode, guard=input_guard)
    elif a.kind == "wait":
        time.sleep(0.5)


def _explicit_action(instruction: str) -> Action | None:
    # Only unambiguous command forms bypass the visual model. Preserve text verbatim.
    match = re.fullmatch(r"(?is)type: ?(.*)", instruction)
    if match:
        return validate_action(Action("type", text=match.group(1), raw=instruction))
    match = re.fullmatch(r"(?i)press(?:: ?| +)([a-z0-9]+(?:\s*\+\s*[a-z0-9]+)*)", instruction.strip())
    if match:
        return validate_action(Action("key", keys=match.group(1), raw=instruction))
    return None


def run_step(i: int, step: Step, vlm: Vlm, mode: str, *, capture_fn=None, stable_fn=None, input_guard=None, preflight: bool = True) -> tuple[StepResult, Frame | None]:
    res = StepResult(i, step.do, "error")
    frame = None
    try:
        frame = (capture_fn or capture)()
        a = _explicit_action(step.do)
        if a is None:
            a = vlm.decide(step.do, frame.downscaled())
        a = validate_action(a)
        res.decide_ms = a.latency_ms
        res.action = _describe(a)
        if a.kind == "invalid":
            res.status = "invalid_action"
            res.note = f"{a.extra.get('reason', 'invalid reply')}: {a.raw.strip()[:240]}"
            return res, frame
        if a.kind == "handback":
            res.status, res.note = "handback", a.extra["reason"]
            return res, frame
        requested_kind = requested_action_kind(step.do)
        if requested_kind and a.kind not in {requested_kind, "done"}:
            res.status, res.note = "handback", f"requested {requested_kind}, model proposed {a.kind}; parent must plan a different action"
            return res, frame
        if a.kind == "done":
            if step.expect:
                ok, ms = vlm.check(step.expect, frame.downscaled())
                reply = getattr(vlm, "last_check_reply", "")
                res.check_reply = reply if isinstance(reply, str) else ""
                res.verify_ms += ms
                res.status = "ok" if ok else "expect_failed"
                res.verified = ok
                res.note = "" if ok else f"expected: {step.expect}"
            else:
                res.status, res.note = "handback", "model says already satisfied; supply an expectation to verify it"
            return res, frame
        if preflight and a.kind in {"click", "double_click", "right_click", "scroll"}:
            region, ms = vlm.active_region(frame.downscaled())
            res.verify_ms += ms
            res.active_region = region
            nx, ny = a.nx if a.nx is not None else .5, a.ny if a.ny is not None else .5
            if region is None or not (region[0] <= nx <= region[2] and region[1] <= ny <= region[3]):
                res.status, res.note = "handback", "proposed pointer is outside the active visual work area or its bounds are uncertain"
                return res, frame
        if preflight and a.kind in {"click", "double_click", "right_click"}:
            visible, ms = vlm.target_visible(step.do, frame.downscaled())
            res.verify_ms += ms
            if not visible:
                res.status, res.note = "handback", "visual preflight could not confirm the requested target"
                return res, frame
        if input_guard is not None and not input_guard():
            res.status, res.note = "error", "input guard rejected action"
            return res, frame
        t0 = time.perf_counter()
        _execute(a, frame, mode, input_guard=input_guard)
        res.act_ms = (time.perf_counter() - t0) * 1000
        t0 = time.perf_counter()
        after = (stable_fn or wait_stable)(frame)
        frame_before, frame = frame, after
        if step.expect:
            ok, _ = vlm.check(step.expect, after.downscaled())
            reply = getattr(vlm, "last_check_reply", "")
            res.check_reply = reply if isinstance(reply, str) else ""
            if not ok:
                res.status, res.note = "expect_failed", f"expected: {step.expect}"
                res.verify_ms += (time.perf_counter() - t0) * 1000
                return res, frame
            res.verified = True
        elif a.kind in MUTATING and not has_visible_change(frame_before.image, after.image):
            res.status, res.note = "no_change", "screen did not change after the action; input may have occurred"
            res.verify_ms += (time.perf_counter() - t0) * 1000
            return res, frame
        res.verify_ms += (time.perf_counter() - t0) * 1000
        res.status = "ok"
    except Exception as e:  # Input and verification errors may occur after partial execution.
        res.status, res.note = "error", f"{type(e).__name__}: {e}"
    return res, frame


def run_steps(steps: list[Step], vlm: Vlm, mode: str = "turbo", *, capture_fn=None, stable_fn=None, input_guard=None, preflight: bool = True) -> ChainResult:
    t0 = time.perf_counter()
    out = ChainResult(ok=False, completed=0, total=len(steps))
    frame = None
    for i, step in enumerate(steps):
        if step.risky and not step.confirmed:
            out.steps.append(StepResult(i, step.do, "needs_confirmation", note="risky step not confirmed"))
            out.handback = f"step {i} is flagged risky; resend with confirmed=true to proceed"
            break
        res, frame = run_step(i, step, vlm, mode, capture_fn=capture_fn, stable_fn=stable_fn, input_guard=input_guard, preflight=preflight)
        out.steps.append(res)
        if res.status != "ok":
            out.handback = f"step {i} ({step.do!r}) ended with {res.status}: {res.note}"
            break
        out.completed += 1
    out.ok = out.completed == out.total
    out.final_frame = frame
    out.total_ms = (time.perf_counter() - t0) * 1000
    return out
