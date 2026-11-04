# cu-s1

A local Windows visual executor for a planning agent. Give it a selected window
and a bounded sequence of actions; it uses screenshots, a small local vision
model and native input, then returns results or hands back when uncertain.
Version 0.2 provides a browser control panel and an MCP bridge backed by the same
local execution service.

**The idea: plan big, act local.** A frontier planner (the head) writes a short
chain of steps; cu-s1 (the hand) executes it with a 2B vision model running on
your PC, checks each step on screen, and hands back instead of guessing.

## Demo (real applications, 5 Nov 2026)

Plans were sent over the real MCP bridge; each run is recorded in
[`bench/runs/real-apps/demo/`](bench/runs/real-apps/demo/).

| Task (real app, live) | Result | Wall time |
|---|---|---|
| Wikipedia: open *Alan Turing*, jump to *Legacy* (Edge, InPrivate) | 3/3 verified | 9.5 s |
| Windows Calculator: 9 visual button clicks, 765 verified on screen | 9/9 | 16.2 s |
| File Explorer: create, name and open a folder | 3/3 | 6.0 s |
| Asked to click a non-existent "Delete my account" button | handed back, no input sent | 6.0 s |

For contrast, a frontier model driving Chrome by looking at every screenshot
(Claude in Chrome) took 69 s for the same Wikipedia task — but it also worked out
the steps itself, while cu-s1 was handed a 3-step plan. That difference is the
point of the split, not a like-for-like model comparison.

The panel's monitor view (`http://127.0.0.1:<port>/?monitor`) shows a live timer
and per-step progress — action taken, time, and whether the expected result was
verified on screen — for plans arriving from the panel or over MCP.

## Built with Meta

Built during the Meta Global AI Developer Hackathon (26 Oct – 4 Nov 2026).
Muse Code produced much of the scaffolding around the executor: the MCP bridge,
the control panel and the benchmark harness. The Meta Model API helped write the
case generator and test fixtures. Muse Wonder was run as the planner over cu-s1
through Muse Code during the build. cu-s1 is designed to sit under a planner like
Muse Wonder: the frontier model stays the head; cu-s1 is the hand. No Meta model
runs inside the executor itself — the local vision model is Qwen3-VL 2B.

## Quick start

1. Use Windows with Python 3.11–3.13 (the development workspace uses 3.12).
   Install and start Ollama, and make sure `qwen3-vl:2b-instruct` is available.
2. Double-click `setup-cu-s1.cmd` to prepare dependencies and the vision model.
   With Python 3.12 and Ollama installed, setup requires no developer commands.
   Alternatively, in PowerShell at the project root:

   ```powershell
   py -3.12 -m venv .venv
   .venv\Scripts\python.exe -m pip install -e .
   ollama pull qwen3-vl:2b-instruct
   ```

   Skip the pull if the model is already installed. The first model request may
   take longer while it loads.
3. Double-click `launch-cu-s1.cmd`. It starts the local service and opens the
   control panel in your browser. If the service is already running, the launcher
   opens its existing panel. Alternatively run `.venv\Scripts\python.exe -m cu_s1.app`.
4. Choose a visible target window and add one action per step. Add an expected
   visible result when needed, then choose **Run steps**. The selected window is
   brought to the foreground. Use **Stop** to request a cooperative stop and
   review the result and final view before continuing.

Minimized windows must be restored first; the target must be fully visible on the
primary display. An in-flight model request may finish after Stop is requested.
A result showing a screen change alone does not prove the intended outcome;
provide expectations and review handbacks.

## MCP integration

The project-scoped `.codex/config.toml` launches `cu_s1.bridge`; restart or reload
the MCP client after changing its configuration or the bridge code. For another
client, adapt `examples/codex-config.toml` to your Python and project paths. The
bridge starts the same local service if necessary, so the panel and bridge share
one execution engine and overlapping chains are rejected. Use the bridge rather
than launching `cu_s1.server` directly when sharing the panel's engine.

- `windows()` lists visible window titles and handles.
- `look(target_hwnd)` activates and captures the selected window.
- `run_steps(steps, mode="turbo", target_hwnd=...)` activates the selected window
  and executes up to 64 steps. The handle must come from `windows()`.
- `stop()` requests a cooperative stop. MCP protocol cancellation also requests
  stop for the submitted job; cancelling only a client-side wait may not send
  the server a protocol cancellation notification.

```json
{
  "target_hwnd": 123456,
  "mode": "turbo",
  "steps": [
    {"do": "Click inside the Note text field."},
    {"do": "Type: cedar-47", "expect": "The Note field contains cedar-47."},
    {"do": "Click Apply.", "expect": "The status says COMPLETE."}
  ]
}
```

Replace the example handle with an observed handle. Each `do` describes one
orchestrated action. `Type:` and `Press Ctrl+Enter` preserve literal text and
bypass model generation. Supply `risky: true` for an action needing explicit
confirmation and `confirmed: true` only when that confirmation has been given;
risk is not detected automatically. `mode="human"` selects human-style movement
and typing. Do not retry an ambiguous action automatically: it may already have
had an effect.

The executor uses visual presence checks and window/focus guards, but these are
fallible. `ok` means the configured checks passed, and `verified` refers to a
visible expectation; neither proves the overall goal or causation. A parent agent
should retain responsibility for planning and recovery.

## Configuration and troubleshooting

Choose **Check model** in the panel, or run a diagnostic without accessing the
desktop:

```powershell
.venv\Scripts\python.exe -m cu_s1.doctor --json
.venv\Scripts\python.exe -m cu_s1.doctor --warmup --json
```

Warmup sends a synthetic image; it measures request acceptance and latency, not
visual accuracy. If the backend or model is unavailable, start Ollama and check
that the configured model is installed. If a target cannot be activated, restore
it, ensure it is fully on the primary display, refresh the window list and select
it again. If the panel does not open, run the module command above in a terminal
to see startup errors. Reload the MCP client after configuration changes.

| Variable | Default | Purpose |
|---|---|---|
| `CU_S1_MODEL` | `qwen3-vl:2b-instruct` | Vision model name |
| `CU_S1_BACKEND` | Ollama, or OpenAI-compatible when a base URL is supplied | Serving protocol |
| `CU_S1_BASE_URL` | `http://localhost:11434` for Ollama | Server root URL |
| `CU_S1_SCALE` | `1000` | Model coordinate scale |
| `CU_S1_JSON` | `1` | Enable structured action output where supported |
| `CU_S1_MAX_SIDE` | `1280` | Maximum model-input side, 320–1920 pixels |
| `CU_S1_HOME` | unset | Override the service runtime directory |

The service listens on loopback with a random port and mutation token. In an
editable workspace its service record is `.runtime/service.json`; an installed
package uses `%LOCALAPPDATA%\cu-s1\service.json`. `CU_S1_HOME` overrides either
location. The record contains a token, so keep it private. The panel and bridge
must use the same runtime directory and environment to share a service. Changing
model settings requires restarting the running service.

## Validation and limitations

Run the automated tests with:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Only use disposable fixtures for live tests. The reserved holdout seeds 8, 19 and
31 produced **8/9** local completions; one visible Economy option was falsely
rejected. Three matched supplied-plan tasks completed **3/3** for both the local
executor and built-in baseline, with execution medians of **6.848 s** and
**25.582 s**, respectively. Setup and parent delegation generation were excluded.
These small samples do not establish general accuracy or speed superiority. See
[`bench/runs/holdout-comparison-v8.json`](bench/runs/holdout-comparison-v8.json),
[`bench/runs/holdout-final-v8.json`](bench/runs/holdout-final-v8.json), and
[project status](PROJECT_STATUS.md). Earlier entries in
[benchmark results](bench/results.md) describe the state at their original cutoff;
the latest v9 section supersedes the old pause and unrun-holdout statements.
The fresh shared-service bridge release run completed **9/9**, median **5.177 s**,
without a paired built-in baseline on those seeds. An earlier bridge run was
8/9 after a guarded interruption; both records are retained.

On the audited 35-image grounding set, the tested native-format GUI-Owl and
UI-Venus paths scored 30/35 and 32/35; the default Qwen path scored 31/35.
These are model-only results under their tested serving configurations, not a
complete comparison of end-to-end systems. Generalization remains unproven.
