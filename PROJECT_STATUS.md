# Project status — 2026-11-05

The 21:00 IST handoff deadline on 2026-11-04 was missed. Work continued after
that deadline; the remaining release checks below are not yet complete. The
user stopped computer use with physical Escape around00:25IST November5.
No desktop capture/control may resume without explicit authorization; code,
backend checks and saved-image evaluations may continue.

## Product and decision

cu-s1 0.2 is a Windows local visual executor: the parent plans and recovers, and
the executor handles bounded actions from screenshots. The local browser panel
and `cu_s1.bridge` share one loopback service and one execution engine. The
launcher opens the panel; the bridge exposes `windows`, `look`, `run_steps`, and
`stop`. A chosen window is explicitly activated and remains subject to the core
focus and geometry guards. The service uses a random token for mutations and a
local service record; `CU_S1_HOME` can override its runtime directory. See the
[README](README.md) for setup and usage.

Retain `qwen3-vl:2b-instruct` via Ollama and 1280 maximum input side as the
default. On the audited 35-image set, the native-format GUI-Owl 1.5 2B path
scored **30/35**, UI-Venus 1.5 2B **32/35**, and default Qwen **31/35**. These
model-only results are under their respective tested prompts and serving
configurations; they do not establish that Qwen outperformed both alternatives.
The optional Qwen 2B/1920 profile scored 32/35 with a median 841 ms versus
687 ms at 1280. The tested 4B candidate scored 32/35 with 1078 ms median and did
not meet the frozen 33/35 promotion threshold. No fine-tuning was performed.

The competitive decision remains a scoped local execution adapter. A general
accuracy, speed or capability advantage over built-in computer use or other
systems has not been established.

## Evidence

- Reserved live holdout seeds 8, 19 and 31: **8/9** local completions. A visible
  Economy option was falsely rejected. The independently scored raw record is
  `bench/runs/holdout-final-v8.json`.
- On three matched supplied-plan holdout tasks, the local executor and built-in
  baseline each completed **3/3**. Median execution times were **6.848 s** local
  and **25.582 s** built-in. Setup and parent delegation generation were
  excluded. The matched subset does not erase the failure in the full 8/9
  holdout. See `bench/runs/holdout-comparison-v8.json`.
- Earlier expanded development fixtures: local **12/12** versus built-in
  **6/6**, with pooled medians **4.712 s** and **28.995 s**. This is a small
  development benchmark; setup and warmup were excluded. See
  `bench/runs/expanded-summary.json` and `bench/results.md`.
- Independent static holdout: **24/24** positive and **12/12** nonactionable
  cases correct with input replaced by a recorder. These are not live task
  completions. The earlier live holdout development seeds 0 and 1 completed 6/6.
- The browser panel completed a four-step disposable fixture run with the fixture
  reporting COMPLETE. This is a scoped UI smoke test, not a complete release
  certification.
- The current full unit suite reports **67 tests passed**, covering the executor,
  product API, runtime paths, activation and delayed-submission cancellation.
- Native-format candidate grounding evidence is retained in
  `bench/runs/owl-native-v8.json` and `bench/runs/venus-native-v8.json`.
  `bench/results.md` contains historical cutoff statements, including that the
  reserved holdout was unrun; the v8 records above supersede those statements.

## Verified 0.2 delivery

- Browser Run completed 4/4 steps with independent fixture COMPLETE, including
  the formerly interrupted seed83 registration layout. Model connection and
  Look controls worked. Evidence: `bench/runs/product-dashboard-v9.json` and PNG.
- The panel displayed a real MCP-originated 20-step job and its Stop button
  stopped that same job. The engine became idle, the summary marked remaining
  steps not run, and the fixture recorded no input events. Evidence:
  `bench/runs/product-panel-stop-v9.json` and PNG.
- Real MCP transport discovered all four bridge tools, rejected overlap, handled
  a cancellation notification with zero fixture input events, released the engine
  and successfully captured again. Evidence: `bench/runs/product-mcp-v9.json`.
- Fresh seeds101/127/151 completed 9/9 through the shared bridge, independently
  scored, median5.177s. The prior41/57/83 suite was8/9 due to an input guard
  interruption; its triggering focus/geometry condition was not logged. Both
  results are retained. This does not establish unseen cross-application breadth.
- Full suite:67/67 tests after shared activity changes; dependency compatibility
  and compilation passed. `bench/runs/product-tests-v9.txt` is the actual log.
- Current wheel rebuilt and reinstalled in an isolated environment. Its packaged
  HTML and app match checkout bytes, and its daemon served health, HTML and idle
  activity outside the checkout. See `bench/runs/product-wheel-v9.json`.
- `setup-cu-s1.ps1 -SkipModelDownload` ran successfully, synchronized the locked
  environment and verified the installed vision backend. The full first-download
  branch relies on standard Ollama pull and was not redownloaded in this check.

## Real-application session (2026-11-05, 01:30–02:00 IST, user-reauthorized)

- Real apps driven over the real MCP bridge, results in `bench/runs/real-apps/`:
  Wikipedia in InPrivate Edge 3/3 (9.5 s), Calculator 9/9 visual clicks with 765
  verified (16.2 s), File Explorer 3/3 (6.0 s), non-existent target handed back with
  no input. Notepad was dropped: Windows 11 Notepad merges files into one window
  with the user's open tabs, so it was not a safe target.
- Comparison: a frontier model via Claude in Chrome (screenshot each step) took
  69 s on the same Wikipedia task while also planning; cu-s1 was given the plan.
- Fixes: background-process window activation now falls back to a single Alt tap
  (Windows foreground lock), covered by a unit test; the panel shows live
  per-step progress and timing (also for MCP-originated plans) and has a
  `?monitor` view. Full suite: 79 tests passing.
- Desktop control remains limited to demo fixtures, the throwaway Edge profile,
  Calculator and `C:\cu-s1-demo`.

## Remaining scope of the active goal

The product can be launched and used now as the parent's bounded local Windows
execution layer. It is not proven as a full general replacement for built-in
computer use. Drag and virtual-desktop window capture have now been implemented and tested
with mocked input/display layouts, including negative monitor origins and display
gaps. The current full suite passes75 tests. They remain unverified on live drag
and multiple-monitor setups because of the desktop stop. The preserved0.2 wheel
was built before these additions; the working tree is newer. Broad real-application
reliability and superiority over complete competitor stacks remain unproven. These limitations remain part of the goal
rather than being silently removed from its definition. No fine-tuning was done
because a representative training and evaluation split has not been established.
