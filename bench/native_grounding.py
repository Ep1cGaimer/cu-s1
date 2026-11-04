"""Compare saved-image grounding only using published model-specific protocols.

Requires an already-running local OpenAI-compatible vision server. This program
never launches a server, captures a screen, or executes predicted actions.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import io
import ipaddress
import json
import math
from pathlib import Path
import re
import time
from urllib.parse import urlsplit
import httpx
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
CASE_ROOT = ROOT / 'bench/cases'
OWL_SOURCE = 'https://github.com/X-PLUG/MobileAgent/blob/main/Mobile-Agent-v3.5/grounding_and_kb/eval_grounding_benchmarks.py'
VENUS_SOURCE = 'https://arxiv.org/pdf/2602.09082#page=28'

# Author evaluator's two-action system prompt and optional infeasible prefix.
OWL_SYSTEM = '''# Tools

You may call one or more functions to assist with the user query.

You are provided with function signatures within <tools></tools> XML tags:
<tools>
{"type": "function", "function": {"name": "computer_use", "description": "Use a mouse to interact with a computer.\\n* The screen's resolution is 1000x1000.\\n* Make sure to click any buttons, links, icons, etc with the cursor tip in the center of the element. Don't click boxes on their edges unless asked.\\n* don't use any other computer use tool like type, key, scroll, left_click_drag and so on.\\n* you can only use the left_click and mouse_move action to interact with the computer. if you can't find the element, you should terminate the task and report the failure.", "parameters": {"properties": {"action": {"description": "The action to perform. The available actions are:\\n* `mouse_move`: Move the cursor to a specified (x, y) pixel coordinate on the screen.\\n* `left_click`: Click the left mouse button with coordinate (x, y) pixel coordinate on the screen.", "enum": ["mouse_move", "left_click"], "type": "string"}, "coordinate": {"description": "(x, y): The x (pixels from the left edge) and y (pixels from the top edge) coordinates to move the mouse to. Required only by `action=mouse_move` and `action=left_click`.", "type": "array"}}, "required": ["action"], "type": "object"}}}
</tools>

For each function call, return a json object with function name and arguments within <tool_call></tool_call> XML tags:
<tool_call>
{"name": <function-name>, "arguments": <args-json-object>}
</tool_call>
'''
OWL_REFUSAL = '''Additionally, if you think the task is infeasible (e.g., the task is not related to the image), return <tool_call>
{"name": "computer_use", "arguments": {"action": "terminate", "status": "failure"}}
</tool_call>'''
# UI-Venus-1.5 report appendix A.2; paper wraps the text across lines.
VENUS_TEMPLATE = ('Output the center point of the position corresponding to the following instruction: {problem}.\n'
                  'The output should just be the coordinates of a point, in the format [x,y]. Additionally, if the\n'
                  'task is infeasible (e.g., the task is not related to the image), the output should be [-1,-1].')
PAIR = re.compile(r'[\[(]\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*[\])]')


def point(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2 or any(type(x) not in (int, float) or not math.isfinite(x) for x in value):
        raise ValueError('invalid coordinate')
    x, y = value
    if (x, y) == (-1, -1): return 'handback', None
    if not (0 <= x <= 1000 and 0 <= y <= 1000): raise ValueError('coordinate outside 0..1000')
    return 'point', [x / 1000, y / 1000]


def parse(model, message):
    text = message.get('content') or ''
    calls = message.get('tool_calls') or []
    structured = []
    for call in calls:
        fn = call.get('function', {})
        args = fn.get('arguments', '{}')
        args = json.loads(args) if isinstance(args, str) else args
        structured.append({'name': fn.get('name'), 'arguments': args})
    for fragment in re.findall(r'<tool_call>\s*(.*?)\s*</tool_call>', text, re.S):
        structured.append(json.loads(fragment))
    if model == 'owl' and not structured and text.lstrip().startswith('{'):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict) and 'name' in obj and 'arguments' in obj:
                structured.append(obj)
        except json.JSONDecodeError:
            pass
    if structured:
        if model != 'owl' or len(structured) != 1: raise ValueError('ambiguous tool calls')
        call = structured[0]
        if call.get('name') != 'computer_use': raise ValueError('unexpected tool')
        args = call.get('arguments')
        if not isinstance(args, dict): raise ValueError('invalid arguments')
        if args.get('action') == 'terminate' and args.get('status') == 'failure': return 'handback', None
        if args.get('action') not in ('left_click', 'mouse_move'): raise ValueError('unexpected action')
        return point(args.get('coordinate'))
    # Accept one bracket/parenthesis pair only; never treat unparseable output as a refusal.
    matches = PAIR.findall(text)
    if len(matches) != 1: raise ValueError('missing or ambiguous point')
    value = [float(x) for x in matches[0]]
    if model == 'owl' and value == [-1, -1]:
        raise ValueError('owl refusal requires a terminate/failure tool call')
    return point(value)


def resize_image(path, max_side):
    with Image.open(path) as im:
        im = im.convert('RGB')
        original = im.size
        if max_side and max(im.size) > max_side:
            scale = max_side / max(im.size)
            im = im.resize((round(im.width*scale), round(im.height*scale)), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format='PNG')
        return original, im.size, base64.b64encode(buf.getvalue()).decode('ascii')


def score(case, action, xy, original):
    negative = case.get('absent', False) or case.get('expected_action') == 'handback'
    if negative: return action == 'handback'
    if action != 'point': return False
    x0, y0, x1, y1 = case['bbox']
    x, y = xy[0] * original[0], xy[1] * original[1]
    return x0 <= x < x1 and y0 <= y < y1


def local_url(value):
    url = urlsplit(value)
    if url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password:
        raise ValueError('base URL must be a local HTTP(S) endpoint without credentials')
    try: local = ipaddress.ip_address(url.hostname).is_loopback
    except ValueError: local = url.hostname.lower() == 'localhost'
    if not local: raise ValueError('base URL must be loopback')
    return value.rstrip('/')


def run(args):
    manifest = args.manifest.resolve()
    cases = json.loads(manifest.read_text(encoding='utf-8-sig'))
    system = OWL_SYSTEM + '\n' + OWL_REFUSAL if args.kind == 'owl' else None
    results = {'model': args.model, 'kind': args.kind, 'source': OWL_SOURCE if system else VENUS_SOURCE,
               'system_prompt': system, 'user_prompt_template': '{instruction}' if system else VENUS_TEMPLATE,
               'coordinate_scale': 1000, 'input_max_side': args.max_side or None,
               'temperature': 0, 'max_tokens': args.max_tokens,
               'manifest_sha256': hashlib.sha256(manifest.read_bytes()).hexdigest(),
               'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               'note': 'Model-only grounding; llama.cpp image preprocessing and generation differ from author evaluation. Parse errors are failures, not refusals.',
               'cases': []}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    def save(): args.out.write_text(json.dumps(results, indent=2), encoding='utf-8')
    with httpx.Client(base_url=local_url(args.base_url), timeout=args.timeout, trust_env=False) as client:
        for case in cases:
            row = {'id': case['id'], 'instruction': case['instruction'], 'expected_action': case.get('expected_action', 'handback' if case.get('absent') else 'click')}
            started = time.perf_counter()
            try:
                path = (CASE_ROOT / case['image']).resolve()
                if not path.is_relative_to(CASE_ROOT.resolve()): raise ValueError('image path outside case directory')
                original, sent, data = resize_image(path, args.max_side)
                user_prompt = case['instruction'] if system else VENUS_TEMPLATE.replace('{problem}', case['instruction'])
                messages = []
                if system: messages.append({'role': 'system', 'content': system})
                messages.append({'role': 'user', 'content': [
                    {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + data}},
                    {'type': 'text', 'text': user_prompt}]})
                row.update({'original_size': original, 'sent_size': sent, 'prompt': user_prompt})
                response = client.post('/v1/chat/completions', json={'model': args.model, 'messages': messages,
                    'temperature': 0, 'max_tokens': args.max_tokens})
                response.raise_for_status()
                result = response.json()
                message = result['choices'][0]['message']
                row['response'] = message
                action, xy = parse(args.kind, message)
                row.update({'action': action, 'point_normalized': xy, 'correct': score(case, action, xy, original)})
            except Exception as exc:
                row.update({'correct': False, 'error': f'{type(exc).__name__}: {str(exc)[:300]}'})
            row['latency_ms'] = round((time.perf_counter() - started) * 1000, 2)
            results['cases'].append(row)
            save()
            print(json.dumps({k: row.get(k) for k in ('id', 'correct', 'action', 'latency_ms', 'error')}), flush=True)
    results['summary'] = {'total': len(results['cases']), 'correct': sum(r['correct'] for r in results['cases']),
                          'errors': sum('error' in r for r in results['cases'])}
    save()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--kind', choices=['owl', 'venus'], required=True)
    p.add_argument('--model', required=True, help='Model name exposed by local server')
    p.add_argument('--base-url', default='http://127.0.0.1:8089')
    p.add_argument('--manifest', type=Path, default=CASE_ROOT/'audited.json')
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--max-side', type=int, default=1280, help='Maximum input side; 0 means native')
    p.add_argument('--max-tokens', type=int, default=128)
    p.add_argument('--timeout', type=float, default=120)
    args = p.parse_args()
    if args.max_side < 0 or args.max_tokens < 1 or args.timeout <= 0: p.error('invalid size, token budget or timeout')
    run(args)


if __name__ == '__main__': main()
