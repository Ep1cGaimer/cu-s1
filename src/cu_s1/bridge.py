"""FastMCP proxy to the local product service; shares its single executor."""
from __future__ import annotations

import asyncio
import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request

from mcp.server.fastmcp import FastMCP, Image
from .server import StepInput
from .paths import runtime_location

RUNTIME, WORKDIR = runtime_location()
SERVICE_FILE = RUNTIME / 'service.json'
mcp = FastMCP('cu-s1')
# Keep cancellation cleanup alive independently of an MCP request task.
_cleanup_tasks: set[asyncio.Task] = set()


def request(info, path, data=None, timeout=10):
    url = f"http://127.0.0.1:{int(info['port'])}{path}"
    body = None if data is None else json.dumps(data).encode('utf-8')
    headers = {'X-CU-S1-Token': info['token']}
    if body is not None:
        headers['Content-Type'] = 'application/json'
    req = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            message = json.load(exc).get('error', 'Service request failed')
        except Exception:
            message = 'Service request failed'
        raise RuntimeError(message) from None


def discover(wait=0):
    deadline = time.monotonic() + wait
    while True:
        try:
            info = json.loads(SERVICE_FILE.read_text(encoding='utf-8'))
            if type(info.get('port')) is not int or not 1 <= info['port'] <= 65535 or not isinstance(info.get('token'), str):
                raise ValueError('Invalid service record')
            health = request(info, '/api/health', timeout=1)
            if health.get('ok') is True and health.get('product') == 'cu-s1' and health.get('api_version') == 1:
                return info
        except (OSError, ValueError, KeyError, urllib.error.URLError, RuntimeError):
            pass
        if time.monotonic() >= deadline:
            return None
        time.sleep(.15)


def service():
    info = discover()
    if info:
        return info
    pythonw = Path(sys.executable).with_name('pythonw.exe')
    executable = str(pythonw if pythonw.exists() else Path(sys.executable))
    WORKDIR.mkdir(parents=True, exist_ok=True)
    subprocess.Popen([executable, '-m', 'cu_s1.app', '--no-browser'], cwd=str(WORKDIR),
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    info = discover(wait=15)
    if not info:
        raise RuntimeError('Local executor could not start')
    return info


def decode_image(data):
    prefix = 'data:image/png;base64,'
    if not isinstance(data, str) or not data.startswith(prefix):
        raise ValueError('Invalid screenshot')
    return Image(data=base64.b64decode(data[len(prefix):], validate=True), format='png')


@mcp.tool(name='windows')
def windows() -> list[dict]:
    """List visible windows available for explicit target selection."""
    return request(service(), '/api/windows')['windows']


@mcp.tool(name='look')
def look(target_hwnd: int) -> Image:
    """Activate and capture a selected window."""
    return decode_image(request(service(), '/api/look', {'target_hwnd': target_hwnd}, timeout=40)['screenshot'])


@mcp.tool(name='stop')
def stop() -> dict:
    """Request cooperative stop; an in-flight model request may finish first."""
    return request(service(), '/api/stop', {})


@mcp.tool(name='run_steps')
async def run_steps(steps: list[StepInput], mode: str = 'turbo', target_hwnd: int | None = None) -> list:
    """Execute a bounded chain against an explicitly selected window. Each step has do, optional expect, risky and confirmed fields. Stop and hand back on uncertainty."""
    info = await asyncio.to_thread(service)
    submission = asyncio.create_task(asyncio.to_thread(request, info, '/api/run',
                  {'steps': [s.model_dump() for s in steps], 'mode': mode, 'target_hwnd': target_hwnd}))
    try:
        job_id = (await asyncio.shield(submission))['job_id']
        while True:
            job = await asyncio.to_thread(request, info, '/api/jobs/' + job_id)
            if job['status'] in ('completed', 'handback', 'stopped', 'error'):
                if 'summary' not in job:
                    raise RuntimeError(job.get('error', 'Execution stopped'))
                result = [json.dumps(job['summary'], indent=1)]
                if job.get('screenshot'):
                    result.append(decode_image(job['screenshot']))
                return result
            await asyncio.sleep(.25)
    except asyncio.CancelledError:
        # Native asyncio task is not a child of the MCP request's AnyIO scope.
        # It survives repeated cancellation while the HTTP submission finishes.
        async def stop_submitted_job():
            submitted = await asyncio.shield(submission)
            await asyncio.to_thread(request, info, '/api/stop',
                                    {'job_id': submitted['job_id']}, timeout=5)

        cleanup = asyncio.create_task(stop_submitted_job())
        _cleanup_tasks.add(cleanup)
        def finish(task):
            _cleanup_tasks.discard(task)
            if not task.cancelled():
                task.exception()  # Consume submission/stop failures without leaking tokens.
        cleanup.add_done_callback(finish)
        raise



def main():
    mcp.run()

if __name__ == '__main__':
    main()
