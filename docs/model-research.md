# System 1 model research (2026-10-29)

Goal: a light (<= ~4B) open-weight VLM that picks the next UI action from a screenshot + instruction,
fast on an 8 GB RTX 4060 laptop, and that **generalizes to unfamiliar surfaces**.

All scores are vendor/third-party reported with different harnesses; treat as hints. Our own bake-off decides.

| Model | Size | License | Reported grounding | Notes |
|---|---|---|---|---|
| Qwen3-VL-2B/4B-Instruct | 2B/4B | Apache-2.0 | 2B: 86.7 avg ScreenSpot-v2 (3rd-party) | Baseline. Ollama tag `qwen3-vl:2b` is the THINKING variant (wastes tokens); use `-instruct` tags |
| **GUI-Owl-1.5-2B/4B-Instruct** (mPLUG) | 2B/4B | MIT | End-to-end OSWorld-Verified **43.5 (2B) / 48.2 (4B)**; 80.3 ScreenSpot-Pro is for the largest size only | Built on Qwen3-VL. **Outputs relative 0-1000 coords by default** (official README). GGUF + mmproj exist (mradermacher) |
| **Holo2-4B** (H Company) | 4B | Apache-2.0 | **ScreenSpot-Pro 57.2, OSWorld-G 69.4**, ScreenSpot-v2 93.2 (vs Qwen3-VL-4B-Thinking 41.4 / 56.4); navigation OSWorld 37.7, AndroidWorld 64.6 | Fine-tuned from Qwen3-VL-4B-Thinking (official page). GGUF exists (mradermacher). Prompt format only in their cookbook |
| **UI-Venus-1.5-2B** (inclusionAI) | 2B | Apache-2.0 (HF tag) | ScreenSpot-Pro **57.7** (8B 68.4) | Has "refusal-aware grounding" (says when the target isn't there, useful for our hand-back). GGUF exists |
| **MAI-UI-2B** (Tongyi-MAI) | 2B | Apache-2.0 | Family headline 73.5 ScreenSpot-Pro / 70.9 OSWorld-G is NOT per-size | Qwen3-VL based. GGUF exists |
| KV-Ground-4B (vocaela) | 4B | ? | 63.2 ScreenSpot-Pro / 94.6 ScreenSpot-v2 | Qwen3-VL-4B fine-tune; unverified provenance, lower priority |
| Qwen3.5-2B/4B | 2B/4B | ? | 3rd-party board: 48 / 60.3 ScreenSpot-Pro | No official numbers found; unverified |
| UI-TARS-1.5-7B, Holo1.5-7B, OpenCUA-7B | 7B | Apache | SSPro 39-58 | Too big for the latency/VRAM target |
| Meta Llama 3.2 Vision | 11B+ | Llama | none found | No Meta model is a fit for the executor |

Key practical facts
- Three of the candidates (GUI-Owl-1.5, MAI-UI, UI-Venus-1.5) are Qwen3-VL fine-tunes, so the same serving stack and 0-1000 relative-coordinate convention apply. Their model cards do not publish a prompt format; our generic JSON-action prompt is the first thing to try, native prompts second.
- Holo2-4B is the strongest *grounding* number at 4B (OSWorld-G 69.4); GUI-Owl-1.5 has the strongest *end-to-end small-model agent* number (OSWorld-Verified 43.5 at 2B).
- ScreenSpot-Pro is high-res professional apps; OSWorld-G is 1080p standard UIs. Neither is Windows-taskbar-specific, so we add our own real-desktop cases.
- Eval settings (max_pixels) move scores a lot; small targets vanish if the screenshot is downscaled too far.

Serving plan: llama.cpp `llama-server` (CUDA build) with GGUF + `--mmproj`; avoids a PyTorch install on Python 3.14/3.12 and fits 8 GB VRAM. Fallback: Ollama (`qwen3-vl:*-instruct` only).

Bake-off set (this machine): 20 generated unfamiliar-surface pages (icon-only buttons, chrome-less text) + real-desktop cases auto-labeled from the Windows UI Automation tree (ground truth only; never used to act).

Sources: https://www.perea.ai/research/gui-grounding-models-2026 · https://hub.hcompany.ai/models/Holo2/aboutholo2 · https://huggingface.co/Hcompany/Holo2-4B · https://huggingface.co/mPLUG/GUI-Owl-1.5-32B-Instruct · https://github.com/X-PLUG/MobileAgent/tree/main/Mobile-Agent-v3.5 · https://huggingface.co/inclusionAI/UI-Venus-1.5-2B · https://huggingface.co/Tongyi-MAI/MAI-UI-2B · https://arxiv.org/abs/2602.16855 · https://arxiv.org/abs/2512.22047 · https://arxiv.org/abs/2602.09082
