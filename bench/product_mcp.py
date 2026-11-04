"""Exercise the real shared product bridge on the disposable holdout fixture."""
from __future__ import annotations
import asyncio
import json
import os
from pathlib import Path
import sys
import time
import httpx
from mcp import ClientSession, StdioServerParameters, types
from mcp.client.stdio import stdio_client
from cu_s1.bridge import discover, request

ROOT = Path(__file__).resolve().parents[1]

async def main():
    info = discover()
    if not info:
        raise RuntimeError('Start the product service first')
    windows = request(info, '/api/windows')['windows']
    hwnd = next(w['hwnd'] for w in windows if w['title'] == 'CU-S1 Holdout Benchmark')
    with httpx.Client(base_url='http://127.0.0.1:8096', timeout=15) as fixture:
        setup = fixture.post('/reset', params={'scenario': 2, 'seed': 83}).json()
        params = StdioServerParameters(command=sys.executable, args=['-m', 'cu_s1.bridge'],
                  cwd=str(ROOT), env={**os.environ, 'PYTHONUTF8': '1'})
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as client:
                await client.initialize()
                tools = [t.name for t in (await client.list_tools()).tools]
                assert sorted(tools) == ['look', 'run_steps', 'stop', 'windows']
                first = asyncio.create_task(client.call_tool('run_steps', {
                    'steps': setup['steps'], 'mode': 'turbo', 'target_hwnd': hwnd}))
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    activity = await asyncio.to_thread(request, info, '/api/activity')
                    if activity['busy'] and activity['kind'] == 'run':
                        break
                    await asyncio.sleep(.01)
                else:
                    raise AssertionError('MCP job never reached the product service')
                job_id = activity['job']['id']
                busy = await client.call_tool('run_steps', {
                    'steps': [{'do': 'Click the Registration code text field.'}], 'target_hwnd': hwnd})
                assert busy.isError, 'Overlapping bridge call was not rejected'
                request_id = next(iter(client._response_streams))
                await client.send_notification(types.ClientNotification(types.CancelledNotification(
                    params=types.CancelledNotificationParams(requestId=request_id, reason='Product cancellation test'))))
                try:
                    await asyncio.wait_for(first, 10)
                except Exception:
                    pass  # MCP reports cancellation as an error response.
                deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    activity = await asyncio.to_thread(request, info, '/api/activity')
                    if not activity['busy']:
                        break
                    await asyncio.sleep(.1)
                assert not activity['busy'], 'Cancelled bridge call left the engine busy'
                job = request(info, '/api/jobs/' + job_id)
                assert job['stop_requested'] and job['status'] == 'stopped'
                truth = fixture.get('/state').json()
                assert not truth['events'], 'Input occurred before the cancellation check'
                idle = await client.call_tool('stop', {})
                assert not json.loads(next(c.text for c in idle.content if c.type == 'text'))['active']
                look = await client.call_tool('look', {'target_hwnd': hwnd})
                assert not look.isError and any(c.type == 'image' for c in look.content)
        result = {'tools': tools, 'actual_stdio_bridge': True, 'overlap_rejected': True,
                  'protocol_cancellation_stopped_shared_job': True,
                  'events_after_cancel': truth['events'], 'engine_released': True,
                  'look_after_cancel_has_image': True, 'cancelled_job_status': job['status']}
        path = ROOT / 'bench/runs/product-mcp-v9.json'
        path.write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result))

if __name__ == '__main__':
    asyncio.run(main())
