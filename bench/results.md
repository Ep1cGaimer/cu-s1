# Local System 1 evaluation — 2026-11-04

## Product validation — 2026-11-05

The 21:00 IST deadline on November 4 was missed. Laptop use was reauthorized
around 20:01 IST, and the subsequent records supersede the historical pause
and unrun-holdout statements below.

- The original reserved live seeds 8/19/31 completed **8/9**. Economy was visible
  but the presence predicate rejected it. This failure remains in
  `runs/holdout-final-v8.json`; those seeds are now development data.
- Built-in baseline completed 3/3 matched supplied-plan cases. Local execution
  also completed 3/3 on that subset, median **6.848 s** versus **25.582 s**.
  Setup and delegation generation are excluded. The subset does not erase the
  full-suite failure. See `runs/holdout-comparison-v8.json`.
- A shorter presence statement was checked against all 36 independent saved-image
  cases before adoption: **36/36**, including 12 nonactionable targets. This is
  recorded in `runs/direct-presence-probe-v8.json`; input was a recorder.
- The first fresh shared-service/bridge suite, seeds 41/57/83, completed **8/9**.
  The last task selected the correct symbol, then the input guard rejected the
  next action. It was a guarded interruption rather than a presence rejection;
  the triggering focus/geometry condition was not recorded, so its cause is
  unresolved. Earlier stale-service activation failures are also retained.
- After restarting the service with the current activation code, fresh seeds
  101/127/151 completed **9/9** through actual stdio `cu_s1.bridge`, independently
  scored by fixture events. Median execution **5.177 s**, including the first
  trial at 7.323 s. There is no paired built-in baseline on these seeds. Source
  hashes match at run start and end. See `runs/product-bridge-release-v9.json`.
- The rebuilt 0.2 wheel contains the HTML and imports from an isolated environment
  outside the checkout. An installed-wheel daemon served its health endpoint and
  panel with `CU_S1_HOME` overridden. The current full automated suite passes
  **67 tests**. The final dashboard completed4/4, and its Stop button stopped a real
  MCP-originated job; actual protocol cancellation also stopped a shared job
  with zero fixture input events. See `runs/product-{dashboard,panel-stop,mcp,wheel}-v9.json`.
- Official-format model-only tests, adapted to llama.cpp: GUI-Owl **30/35** and
  UI-Venus **32/35**, versus Qwen default **31/35**. These replace any implication
  that generic JSON prompting established a best-configuration model ranking.
  See `runs/owl-native-v8.json`, `runs/venus-native-v8.json` and
  `bench/native_grounding.py` for prompts, parsing and serving differences.

These measurements support lower parent-loop latency on scoped workflows.
They do not establish a general replacement, superiority over existing complete
agent stacks, or a comparative safety guarantee. Failures remain part of the record.

## Historical 19:07 IST cutoff (superseded above)

Live computer use and screenshots were paused at about 19:07 IST. Everything
after that used code, backend APIs, synthetic images or previously saved images.
The reserved new live holdout was not run. The v6 live comparisons below remain
valid historical measurements; late cancellation/resolution changes have not
been re-exercised on the desktop.

- Independent static holdout, generator seed 88931: **36/36** correct through
  the current vision/preflight path, with `_execute` replaced by a recorder.
  This comprises 24 positive targets and 12 handbacks (8 missing, 2 modal-blocked,
  2 disabled). No ground-truth bbox enters inference. No prompt changes were
  accepted after seeing these results. This is synthetic out-of-development
  evidence, not live application success or a built-in-MCP comparison.
- Independently built live holdout, development seeds 0/1: **6/6** succeeded
  before the pause. Reserved seeds 8/19/31 remain unrun; they must not be counted
  as passed or used for further tuning and then described as unseen.
- The 2B high-resolution profile recovered Memory subtract: **32/35**, median
  841 ms and p90 1409 ms at maximum side 1920, versus 31/35 and 687 ms at 1280.
  The default remains 1280; the new `CU_S1_MAX_SIDE` option permits 320–1920.
- Qwen3-VL 4B Q4_K_M at 1280: **32/35**, median 1078 ms, p90 1137 ms; initial
  warmup 36.239 s excluded from prediction timings. Total GPU memory use was
  observed at 4399 MiB (not model-only memory). Model manifest/digest are retained.
  It failed the frozen 33/35 promotion gate and was unloaded rather than adopted.
- Compact, no-kind-hint and reconstructed-historical prompt experiments scored
  31/35, 30/35 and 30/35 respectively. None were adopted. All predictions remain
  preserved. The `Windows Update` screenshot has more than one matching label;
  scores retain the original single bbox rather than retroactively granting credit.
- Final code adds an offline diagnostic and cooperative stop/cancellation;
  **57 mocked tests passed**, dependency checks and compilation passed, and a
  fresh stdio client discovered four tools and called idle stop without any
  desktop metadata/capture/input. In-flight model calls may finish before the
  stopped worker exits. Stop prevents new captures/input at cooperative checks.

Primary new evidence: `runs/static-holdout-2b-v7-final.json`,
`cases/holdout-static/audit.json`, `runs/holdout-dev-2b-v6.json`,
`runs/qwen-2b-highres-probe.json`, `runs/qwen-4b-v7-grounding.json`,
`runs/qwen4b-decision.json`, `runs/selection-plan-v7.json`, and
`runs/mcp-protocol-v7.json`.

`runs/mcp-cancellation-v7.json` additionally verifies the real stdio transport with
a synthetic target and worker: stop during a running chain, concurrent rejection,
MCP cancellation notification and cleanup. A local client task cancellation alone
did not notify the server, so this test explicitly sends protocol cancellation.
It performs no desktop metadata reads, screenshots, input or model inference.

For the explicit comparison with existing solutions and the go/no-go decision,
see `docs/competitive-position.md`. A small local visual-agent architecture is
already available elsewhere; a general superiority claim is not supported.

**Decision:** default to `qwen3-vl:2b-instruct` through Ollama, with structured
actions, visual target-presence and modal-boundary checks, and conservative
handback. The final local MCP completed 12/12 trials across six native/browser
tasks, versus the built-in loop's 6/6. Median execution was 4.712 s versus
28.995 s. A general accuracy or capability win is not established.

## Machine and serving

HP OMEN 16-xd0xxx; Ryzen 7 7840HS, 8 cores/16 threads; 15.29 GiB usable RAM;
RTX 4060 Laptop GPU, 8188 MiB VRAM; NVIDIA driver 621.01. Initial available RAM
was only 1.87 GiB. The selected Qwen deployment was observed with approximately
2.9 GiB total GPU memory in use, including the desktop and other GPU consumers.

Qwen was already installed as the 2B instruct Q4_K_M vision model (~1.93 GB on
disk including its packaged assets). GUI-Owl and UI-Venus used Q4_K_M GGUFs plus
Q8 visual projectors, served by llama.cpp b11981 CUDA 12.4 with 8192 context,
one slot, flash attention, and a 1024 image-token budget. The latter assets have
commit IDs and SHA256s in `models/*.provenance.json`; runtime checksums are in
`tools/llama-cuda/verified-release.json`. One inference server was used at a time.

## Expanded native and browser comparison

The second phase adds independently scored WinForms and Edge fixtures: a form,
a scrolling pane/page with a small target, and an owned native or DOM dialog.
The browser form also requires selecting an image of a rising blue line.
All data and actions are disposable and local. Local execution uses a fresh real
stdio MCP process; it receives only screenshots and the supplied instructions.
The evaluator reads the fixtures' event/state logs after execution.

| Execution path | Successful trials | Median execution wall | Range |
|---|---:|---:|---:|
| Parent + built-in `@oai/sky`, accessibility allowed | 6/6 | 28.995 s | 25.078–66.476 s |
| Final local MCP, two repetitions of each task | 12/12 | 4.712 s | 2.747–9.003 s |

The ratio of pooled medians is **6.15x**. Reducing each pair of local repetitions
to one task median gives 4.990 s and a **5.81x** ratio against the six baseline
tasks. Native local median is 4.096 s; browser local median is 5.729 s.

The built-in path may use accessibility and `set_value`; it is not forced to
imitate the local mouse/typing sequence. Its driver calls total only
0.718–1.802 s per task. Full wall times include this parent model's decisions
and tool orchestration. Baseline recoveries remain in the results: an offscreen
click was rejected, a newly opened native modal needed a screenshot before
clicking, and a stale post-action snapshot needed another observation. One
native form snapshot had not updated its status yet, but independent state
confirmed success. These are single baseline trials, not a universal latency
estimate for every parent model or optimized orchestration strategy.

Setup, fixture resets/activation, MCP startup, model warmup, parent planning and
generation of the delegation request are excluded. Cold-shape/prompt costs
inside execution remain included. Excluded warmup was 3.339 s for the browser
run and 12.563 s for the native run; resident operation matters for latency.
There are six distinct development tasks, not twelve held-out tasks. The same
fixtures exposed failures and guided the fixes, so this is a development
benchmark. No trained weights or application-specific coordinates were added.

Final negative MCP trials rejected **6/6** absent, offscreen, and modal-blocked
targets before input, with zero new fixture events. The final modal-boundary
predicate retained all **35/35** audited positive target centers inside its
permitted area. These checks remain fallible visual model judgments.

The original executor succeeded on only **4/6** expanded tasks. Intermediate
failures and rejected approaches are preserved:

- Tiny checked-state changes disappeared in thumbnail comparisons. A full
  resolution fallback now detects them; it remains evidence of change only.
- A visible COMPLETE status was falsely rejected. The verifier now reads text
  near screen edges; all seven saved completion/noncompletion probes passed.
- Excessive scroll values and substituting scrolling for an explicit click
  exposed weak generic JSON output. Ollama now constrains action names, points,
  wheel bounds, and the requested action type; a runtime guard also rejects
  substitutions for backends without schema enforcement.
- Same-process owned native dialogs can be freshly recaptured. Unrelated focus,
  geometry changes and stale modal frames still reject input. Guards now run
  during movement, typing, chords and scrolling, with held-input cleanup.
- A readable background button fooled the yes/no presence check while a DOM
  modal was open. A separate visual modal box now bounds pointer actions.
- A zoomed yes/no coordinate verifier approved all twelve deliberately wrong
  points and one absent label. It was rejected and removed, not enabled.
- Unverified `done` responses now hand back; an explicit expectation is needed
  to accept that work is already complete.

The v4 presence wording accepted 11/12 sampled positives and rejected 10/10
absent labels; the extra conservative false rejection was the Windows theme
image target. The older wording accepted all 12 positives but missed the tiny
browser button and misread status text. Model predicates are not calibrated
confidence, and the modal box does not establish that a point hits the right
control within it. `verified` means the postcondition was visible, not proof
that the input caused it.

Recompute with `bench/summarize_expanded.py`. Primary evidence:
`runs/expanded-summary.json`, `runs/{native,edge}-local-v6.json`,
`runs/{native,edge}-builtin-baseline-v2.json`, `runs/{native,edge}-negatives-v6.json`,
`runs/zoom-verification-probe.json`, and
`runs/modal-region-positive-regression.json`. Final live runs include source hashes.

## Initial visual-only comparison

Each task requires choosing an image-only shape, focusing a note field, typing a
literal string, and clicking a completion button. Three visual themes are used:
light, dark and compact. Completion is scored by an independent native-app event
log. The local model receives only the screenshot and delegated instruction;
the answer key is never given to it.

| Execution path | Independently successful | Median execution wall | Range |
|---|---:|---:|---:|
| Parent model in this chat + built-in `@oai/sky` MCP | 3/3 | 28.601 s | 27.321–30.915 s |
| Qwen local System 1 through actual stdio MCP | 3/3 | 4.056 s | 3.885–6.336 s |
| Qwen direct executor, 12 randomized-layout trials | 12/12 | 3.698 s | 3.636–6.073 s |

The ratio of the first two medians is **7.05x**. The built-in MCP tool time alone
was 0.934–1.432 s, so this is a win over the full observed parent decision loop,
not a claim that native input is faster than the built-in driver. The baseline
used fresh screenshots after each action; Tk's accessibility state exposed only
a pane, so these tasks used pixels. No unrelated work was performed inside the
timed baseline intervals. Fixture setup/activation was excluded.

The local MCP retains target-presence checks, semantic final verification and
focus/geometry guards. The direct executor's twelve seeds vary shape placement
across the same three themes. There were also nine earlier repeated-layout
trials, all successful; those are retained separately and are not pooled into
the twelve varied-layout results.

These are short tasks with a supplied four-step plan. Initial parent planning
and producing the delegation request are outside the timer. Model loading and
cache state vary; early cold Qwen calls took ~8 seconds. Repeated local inputs
can benefit from serving caches. The baseline has only one run per theme and
depends on this chat's model/reasoning/orchestration. There is no claim about
all applications, all parent models, batched driver strategies, or full task
distributions. The built-in MCP was not evaluated on the static target set below.

## Initial static screenshot model comparison

Final scoring uses 35 audited targets: 20 generated unfamiliar icon/text pages
and 15 real-app targets from Calculator, Settings and a Notepad modal. The
original 44-case set included disabled memory controls, a hidden system-menu
target and controls blocked by Notepad's modal; nine cases were excluded by
visual audit. The original manifest and all predictions were preserved.

| Deployment | Correct | Rate | Median prediction | p90 |
|---|---:|---:|---:|---:|
| Qwen3-VL 2B instruct / Ollama | 32/35 | 91.4% | 258 ms | 656 ms |
| GUI-Owl 1.5 2B / llama.cpp CUDA | 30/35 | 85.7% | 591 ms | 639 ms |
| UI-Venus 1.5 2B / llama.cpp CUDA | 28/35 | 80.0% | 464 ms | 619 ms |

All three historical comparison rows use the same action prompt, JSON-constrained output, a
1280-pixel maximum screenshot side and the same targets. The serving runtimes
and model-specific caches differ, so these are deployment comparisons rather
than controlled architecture benchmarks. Warmup is excluded. The positive
set is small and has not been used to train the models in this project.

The raw runs contain 36 predictions from audit version 1. Final scoring drops
the subsequently confirmed disabled `real02` memory-flyout target from **every**
candidate. `bench/summarize.py` recomputes the final table by ID from the current
audited manifest; it does not overwrite the historical predictions.

Qwen still misses `real06` (memory subtract), `real09` (Windows light theme
image) and `real14` (Bluetooth toggle). All twenty generated positive targets
were correct. UI-Venus initially had invalid/prose replies; constraining JSON
improved its score, but it remained behind Qwen. GUI-Owl's native tool-call
prompt and larger image budgets were not evaluated, so this is not its best
possible published performance.

The **current v6 Qwen action path**, rechecked after the additional prompt/schema
constraints, scores **31/35 (88.6%)**, median **687 ms**, p90 **767 ms**, with zero
malformed actions. It retains the three misses above and additionally misses
`real12` (Windows Update). This is a measured grounding regression from the
historical 32/35 comparison, not an accuracy improvement. The new modal/presence
guards and final postconditions help bound execution but do not repair every
wrong coordinate. See `runs/qwen-current-v6-grounding.json`; the historical
three-model results remain unchanged for comparability.

## Initial missing-target evaluation

The action-only prompt was unsafe as an uncertainty detector: Qwen returned
handback for only 3/10 absent-label screens; GUI-Owl and UI-Venus did so for 0/10.
The missing label was `ZEBRA-9QX`, placed in instructions for ten unrelated
screens where it does not exist. Those tests did not execute input.

A separate Qwen visibility predicate then accepted 12/12 sampled positive
targets and rejected 10/10 absent-label screens. UI-Venus also rejected 10/10
absent labels but rejected two real positives. The executor now runs that
predicate before visual clicks and returns control if it fails. This is a
measured guard, not calibrated confidence or a proof of coordinate correctness.

An actual MCP call for the absent label in the native fixture returned handback
with zero mouse/keyboard events. Unit tests separately confirm that a rejected
presence check cannot execute the proposed action.

## Validation and reproduction

- All **38 executor tests passed**. They cover malformed output, literal text, Unicode, no replay,
  failed expectations, explicit handback, strict confirmation, held-input cleanup,
  target presence, modal ownership/boundaries, geometry changes, tiny visual
  changes and focus loss partway through input.
- Real MCP initialize/list-tools/call-tool succeeded. Tools: `windows`, `look`,
  `run_steps`. An unconfirmed risky step stopped; string `"false"` was rejected.
- Editable installation, dependency resolution and Python compilation passed.
- `uv.lock` records dependencies. `mcp>=1.2,<2` avoids the installed v2 breaking
  change that prevented this v1 FastMCP server from starting.

Commands are in `README.md`. Primary evidence:

- `runs/builtin-sky-baseline.json`
- `runs/mcp-acceptance.json`
- `runs/qwen-guarded-heldout.json`
- `runs/summary.json`
- `runs/*-audited-json*.json`, `runs/*-presence.json`, and `cases/audit.json`

## Training decision

No fine-tuning was necessary to obtain these scoped speed wins. Training on a few
synthetic scenes would risk teaching those layouts rather than general behavior.
The next evidence needed is an independently held-out multi-application suite
beyond these development fixtures, with a separate training/held-out split
before any LoRA or other fine-tuning.

Model references: [Qwen3-VL](https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct),
[GUI-Owl 1.5 2B](https://huggingface.co/mPLUG/GUI-Owl-1.5-2B-Instruct),
[UI-Venus 1.5 2B](https://huggingface.co/inclusionAI/UI-Venus-1.5-2B).
Published vendor benchmark scores were not used as local results.
