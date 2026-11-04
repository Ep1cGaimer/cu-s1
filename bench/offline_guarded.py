"""Score the real visual decision/preflight path on saved images; input is replaced by a recorder."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import time
from unittest.mock import patch

from PIL import Image
from cu_s1.runner import Step, run_steps
from cu_s1.screen import Frame
from cu_s1.vlm import Vlm

ROOT = Path(__file__).resolve().parent.parent


def main(args):
    cases = json.loads(args.manifest.read_text(encoding='utf-8'))
    v = Vlm(args.model)
    data = {'model': args.model, 'manifest': str(args.manifest),
            'scope': 'Saved-image grounding plus real preflight; _execute mocked, no desktop capture/input or task completion claim.',
            'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                              for p in sorted((ROOT/'src/cu_s1').glob('*.py'))}, 'cases': []}
    try:
        for c in cases:
            with Image.open(ROOT/'bench/cases'/c['image']) as im:
                frame = Frame(im.convert('RGB'), 0, 0)
            calls = []
            start = time.perf_counter()
            with patch('cu_s1.runner._execute', side_effect=lambda a, *a2, **kw: calls.append(a)):
                r = run_steps([Step(c['instruction'])], v, capture_fn=lambda: frame,
                              stable_fn=lambda before: before, input_guard=lambda: True)
            hit = False
            if c.get('absent'):
                hit = not calls and r.steps[0].status == 'handback'
            elif len(calls) == 1:
                a = calls[0]
                if a.kind == 'click' and a.nx is not None:
                    x, y = a.nx*(frame.size[0]-1), a.ny*(frame.size[1]-1)
                    l, t, right, bottom = c['bbox']
                    hit = l <= x < right and t <= y < bottom
            row = {'id': c['id'], 'kind': c['kind'], 'expected_handback': bool(c.get('absent')),
                   'correct': hit, 'would_act': bool(calls), 'wall_ms': (time.perf_counter()-start)*1000,
                   'decision': asdict(r.steps[0]), 'recorded_actions': [asdict(a) for a in calls]}
            data['cases'].append(row)
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(data, indent=2), encoding='utf-8')
            print(c['id'], c['kind'], hit, row['would_act'], flush=True)
    finally:
        v.client.close()
    print('Correct', sum(r['correct'] for r in data['cases']), '/', len(data['cases']))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest', type=Path, required=True)
    p.add_argument('--model', default='qwen3-vl:2b-instruct')
    p.add_argument('--out', type=Path, required=True)
    main(p.parse_args())
