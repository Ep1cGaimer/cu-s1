# Competitive decision — 2026-11-04

**Decision: continue only as a small local Windows execution adapter for a parent
agent. Do not claim a new GUI-agent architecture or general superiority.** There
is a measured advantage over the observed parent-plus-built-in-MCP loop on six
development tasks. There is no matched local evaluation establishing superiority
over ShowUI, UI-TARS Desktop, OmniTool or mature browser automation.

## Closest alternatives

| Existing option | What it already solves | What our measurements establish |
|---|---|---|
| [ShowUI](https://github.com/showlab/ShowUI) | A 2B vision/action model with local inference, quantization, iterative grounding refinement and computer-use integration. | The small-model concept is already available. No same-machine, official-configuration ShowUI comparison was performed. |
| [UI-TARS Desktop](https://github.com/bytedance/UI-TARS-desktop) and its [SDK](https://github.com/bytedance/UI-TARS-desktop/blob/main/docs/sdk.md) | Local/remote computer and browser operators, visual actions, model-service configuration and integration into agent workflows. | Our bounded MCP contract is an integration choice, not a unique ability to run a local visual agent. No measured speed/accuracy/resource win over this stack. |
| [OmniParser / OmniTool](https://github.com/microsoft/OmniParser) | Visual element parsing, interactability prediction and Windows VM control with selectable vision models. | A direct host-window crop and local model avoid a separate parser in this implementation. That does not prove a better deployment or safety tradeoff. |
| [Playwright MCP](https://github.com/microsoft/playwright-mcp) | Structured accessibility snapshots, exact element references and browser automation without requiring a vision model. | This remains the sensible first choice for browser workflows with usable semantics. Our native/visual fallback does not establish a browser-automation advantage. |

The official pages above were checked on 2026-11-04. Capabilities are descriptions
of existing projects, not independently measured performance claims. Vendor
benchmark scores are not mixed with our local results. The three-model generic
JSON experiment is not a best-configuration evaluation of specialist models.

## Concrete value currently demonstrated

- **Less parent decision overhead on the measured tasks:** six distinct
  WinForms/Edge development tasks, local 12/12 trials versus built-in 6/6, with
  pooled execution medians 4.712 s and 28.995 s. Built-in driver time alone was
  only 0.718–1.802 s; the measured difference is in full decision/orchestration
  loops. Parent planning, delegation generation and startup/warmup are excluded.
- **A working lightweight deployment:** the selected 2B Q4 model is already
  installed through Ollama. No paid inference service or training run is needed
  for its visual decisions. This says nothing about the host planning agent's cost.
- **Explicit execution boundaries:** strict actions, requested-action matching,
  window ownership/geometry guards, held-input cleanup, no blind replay,
  postcondition checks and conservative handback. The independent saved-image
  suite accepted 24/24 positives and rejected 12/12 nonactionable targets before
  the input recorder. This is synthetic evidence, not a guarantee on real apps.

These benefits justify retaining a narrow personal-workflow adapter. They do not
justify rebuilding an entire computer-use framework or claiming a market lead.

## Gaps that existing options already cover better in scope

This executor is Windows-only, requires its bound window fully visible on the
primary display, and does not implement drag. It relies on the parent to declare
risky actions and plan recovery. Presence and modal judgments are fallible;
pixel change does not establish success. General static grounding remains
31/35 at the default input resolution. Browser accessibility can avoid several
of these visual ambiguities. No comparative safety claim is supported.

## Release gate

A claim that this is better than the closest existing alternatives requires
paired identical unseen tasks, recommended competitor prompts/configurations,
independent actual outcome scoring, repeated trials, startup and recovery time,
host-call counts, peak resource use and explicit failure/handback reporting.
The original reserved live holdout completed 8/9; three matched cases completed
3/3 for both built-in and local execution, median 25.582 s versus 6.848 s. A later
fresh bridge suite completed 9/9, median 5.177 s, without a paired baseline on its
seeds. Official-format model-only tests scored GUI-Owl 30/35 and UI-Venus 32/35
against Qwen default 31/35. These results do not establish superiority over full
competitor stacks. See `bench/results.md` for the preserved failures and scope.

**Go:** use this as an opt-in bounded execution layer where the measured reduction
in parent round trips is useful and the parent can verify/recover.
**No-go:** advertise it as generally better, fully autonomous or production-ready
across applications, or replace strong accessibility/API tools solely to use vision.
