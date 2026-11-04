"""Summarize the expanded benchmark without dropping failed or cold trials."""
import json
import statistics
from pathlib import Path

RUNS = Path(__file__).resolve().parent / 'runs'


def load(name):
    return json.loads((RUNS / name).read_text(encoding='utf-8'))


def stats(rows):
    times = [r['wall_ms'] for r in rows]
    return {'trials': len(rows), 'actual_successes': sum(r['actual_success'] for r in rows),
            'median_ms': statistics.median(times), 'min_ms': min(times), 'max_ms': max(times)}


def main():
    result = {'surfaces': {}, 'scope': (
        'Six disposable tasks, two surfaces, supplied bounded plans. Built-in uses this parent model '
        'with accessibility allowed. Local uses real stdio MCP. Setup, warmup, parent planning and '
        'delegation generation are excluded. Trials include cold-shape costs and baseline recoveries. '
        'Development fixtures, not an independent held-out general computer-use benchmark.')}
    baseline_all, local_all, task_medians = [], [], []
    for surface in ('native', 'edge'):
        baseline = load(f'{surface}-builtin-baseline-v2.json')['runs']
        current = load(f'{surface}-local-v6.json')
        local = current['runs']
        assert len(baseline) == 3 and len(local) == 6
        negatives = load(f'{surface}-negatives-v6.json')['cases']
        tasks = []
        for sid in range(3):
            trials = [r for r in local if r['scenario'] == sid]
            b = next(r for r in baseline if r['scenario'] == sid)
            tasks.append({'scenario': sid, 'builtin_ms': b['wall_ms'], 'local': stats(trials)})
            task_medians.append(statistics.median(r['wall_ms'] for r in trials))
        result['surfaces'][surface] = {'builtin': stats(baseline), 'local': stats(local),
            'claimed_successes': sum(r['claimed_success'] for r in local),
            'warmup_ms_excluded': current['warmup_ms'], 'tasks': tasks,
            'negative_handbacks': sum(r['safe_handback'] for r in negatives), 'negative_cases': len(negatives),
            'source_sha256': current['source_sha256']}
        baseline_all += baseline
        local_all += local
    result['builtin'] = stats(baseline_all)
    result['local'] = stats(local_all)
    result['local_matched_task_median_ms'] = statistics.median(task_medians)
    result['ratio_of_pooled_medians'] = result['builtin']['median_ms'] / result['local']['median_ms']
    result['ratio_of_matched_task_medians'] = result['builtin']['median_ms'] / result['local_matched_task_median_ms']
    result['development_history'] = {}
    for version in ('v2-before', 'v3', 'v4'):
        result['development_history'][version] = {}
        for surface in ('native', 'edge'):
            data = load(f'{surface}-local-{version}.json')['runs']
            result['development_history'][version][surface] = {
                'trials': len(data), 'actual_successes': sum(r['actual_success'] for r in data),
                'claimed_successes': sum(r['claimed_success'] for r in data)}
    (RUNS / 'expanded-summary.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
