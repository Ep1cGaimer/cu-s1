"""Run independent seeded holdout against fresh stdio MCP servers.

Start holdout_fixture.py separately and keep its window foreground. Development
seeds: 0,1; final holdout: 8,19,31. Only setup steps reach the MCP model.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import asyncio
import json
import os
from pathlib import Path
import time
import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parent.parent
TITLE = 'CU-S1 Holdout Benchmark'


def summary(result):
    for item in result.content:
        if item.type == 'text':
            try:
                value = json.loads(item.text)
                if isinstance(value, dict) and 'completed' in value:
                    return value
            except ValueError:
                pass
    raise ValueError('MCP response contains no chain summary: ' + ' '.join(
        item.text for item in result.content if item.type == 'text'))


def save(out, results):
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, indent=2), encoding='utf-8')


def source_hashes():
    paths = sorted((ROOT / 'src/cu_s1').glob('*.py')) + [
        ROOT / 'bench/holdout_fixture.py', ROOT / 'bench/holdout_mcp.py', ROOT / 'pyproject.toml']
    return {str(path.relative_to(ROOT)).replace('\\', '/'): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in paths}


def save_frame(result, out, seed, scenario):
    for item in result.content:
        if item.type == 'image' and item.mimeType == 'image/png':
            path = out.with_name(f'{out.stem}-seed{seed}-scenario{scenario}.png')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(base64.b64decode(item.data, validate=True))
            return str(path)
    return None


async def one_run(fixture, hwnd, seed, scenario, model, out, server_module):
    from cu_s1.window import foreground
    response = fixture.post('/reset', params={'scenario': scenario, 'seed': seed})
    response.raise_for_status()
    setup = response.json()
    if 'error' in setup:
        raise RuntimeError(setup['error'])
    instructions = setup['steps']
    await asyncio.sleep(.35)
    if server_module == 'cu_s1.server':
        deadline = time.monotonic() + 45
        while foreground() != hwnd and time.monotonic() < deadline:
            await asyncio.sleep(.1)
        if foreground() != hwnd:
            raise RuntimeError('Holdout window is not foreground; no input was sent')
    params = StdioServerParameters(command=str(ROOT / '.venv/Scripts/python.exe'),
        args=['-m', server_module], cwd=str(ROOT), env={**os.environ, 'PYTHONUTF8': '1', 'CU_S1_MODEL': model})
    start = time.perf_counter()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as client:
            await client.initialize()
            execution_start = time.perf_counter()
            result = await client.call_tool('run_steps', {'steps': instructions, 'mode': 'turbo', 'target_hwnd': hwnd})
            execution_wall_ms = (time.perf_counter() - execution_start) * 1000
            execution = summary(result)
            frame_path = save_frame(result, out, seed, scenario)
    wall_ms = (time.perf_counter() - start) * 1000
    actual_response = fixture.get('/state')
    actual_response.raise_for_status()
    actual = actual_response.json()
    return {'seed': seed, 'scenario': scenario, 'execution_wall_ms': execution_wall_ms,
            'process_and_execution_wall_ms': wall_ms, 'final_frame': frame_path,
            'actual_success': actual['completed'], 'events': actual['events'], 'summary': execution}


async def run(seeds, out, model, server_module='cu_s1.server'):
    from cu_s1.window import list_windows
    windows = [w for w in list_windows() if w['title'] == TITLE]
    if len(windows) != 1:
        raise RuntimeError(f'Expected one {TITLE!r} window, found {len(windows)}')
    hwnd = windows[0]['hwnd']
    results = {'seeds': seeds, 'model': model, 'server_module': server_module, 'source_sha256': source_hashes(), 'runs': []}
    with httpx.Client(base_url='http://127.0.0.1:8096', timeout=15) as fixture:
        for seed in seeds:
            for scenario in range(3):
                print(f'Holdout seed={seed} scenario={scenario}', flush=True)
                try:
                    row = await one_run(fixture, hwnd, seed, scenario, model, out, server_module)
                except Exception as exc:
                    row = {'seed': seed, 'scenario': scenario, 'error': f'{type(exc).__name__}: {exc}'}
                    results['runs'].append(row)
                    save(out, results)
                    raise
                results['runs'].append(row)
                save(out, results)
                print(json.dumps({'seed': seed, 'scenario': scenario, 'actual_success': row['actual_success'],
                                  'reported_ok': row['summary']['ok'], 'execution_wall_ms': round(row['execution_wall_ms']),
                                  'process_and_execution_wall_ms': round(row['process_and_execution_wall_ms'])}), flush=True)
    results['source_sha256_end'] = source_hashes()
    save(out, results)
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default=os.environ.get('CU_S1_MODEL') or 'qwen3-vl:2b-instruct')
    parser.add_argument('--seeds', nargs='+', type=int, default=[8, 19, 31])
    parser.add_argument('--out', type=Path, default=ROOT / 'bench/runs/holdout.json')
    parser.add_argument('--server-module', choices=['cu_s1.server', 'cu_s1.bridge'], default='cu_s1.server')
    args = parser.parse_args()
    if any(not 0 <= seed <= 999999 for seed in args.seeds):
        parser.error('seeds must be between 0 and 999999')
    asyncio.run(run(args.seeds, args.out, args.model, args.server_module))
