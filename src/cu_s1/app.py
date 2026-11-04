"""Loopback product service for the shared executor."""
from __future__ import annotations

import argparse
import asyncio
import base64
import concurrent.futures
import ctypes
import json
import os
from pathlib import Path
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
import webbrowser

from . import server
from .doctor import diagnose
from .paths import runtime_location

RUNTIME, WORKDIR = runtime_location()
SERVICE_FILE = RUNTIME / 'service.json'
WEB = Path(__file__).with_name('web') / 'index.html'
MAX_BODY = 1024 * 1024


def activate_target(hwnd: int) -> None:
    # Importing here makes the explicit foreground verification easy to mock in tests.
    from .window import foreground
    if type(hwnd) is not int or hwnd <= 0 or hwnd not in {w['hwnd'] for w in server.windows()}:
        raise ValueError('Select an available window')
    u = ctypes.windll.user32
    u.IsIconic.argtypes = [ctypes.c_void_p]
    u.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    u.SetForegroundWindow.restype = ctypes.c_int
    if u.IsIconic(hwnd):
        raise RuntimeError('Restore the selected window before running')
    if foreground() == hwnd:
        return
    # Attach to the current foreground thread briefly so the explicit user request
    # can transfer focus even though the browser owns the foreground window.
    u.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    u.GetWindowThreadProcessId.restype = ctypes.c_ulong
    u.AttachThreadInput.argtypes = [ctypes.c_ulong, ctypes.c_ulong, ctypes.c_int]
    u.AttachThreadInput.restype = ctypes.c_int
    current = ctypes.windll.kernel32.GetCurrentThreadId()
    foreground_thread = u.GetWindowThreadProcessId(foreground(), None)
    attached = bool(foreground_thread and foreground_thread != current and
                    u.AttachThreadInput(current, foreground_thread, True))
    try:
        u.SetForegroundWindow(hwnd)
    finally:
        if attached:
            u.AttachThreadInput(current, foreground_thread, False)
    # Foreground activation can complete asynchronously; only the observed HWND
    # determines success, regardless of the API's immediate return value.
    if _wait_foreground(hwnd, foreground, .3):
        return
    # Windows' foreground lock refuses requests from a process that did not receive the
    # last input (e.g. a service started in the background). A lone Alt tap is the
    # documented way to satisfy that rule; it is sent once, then success is re-observed.
    VK_MENU, KEYUP = 0x12, 0x0002
    u.keybd_event(VK_MENU, 0, 0, 0)
    u.keybd_event(VK_MENU, 0, KEYUP, 0)
    u.SetForegroundWindow(hwnd)
    if not _wait_foreground(hwnd, foreground, .5):
        raise RuntimeError('Could not activate the selected window; bring it forward and try again')


def _wait_foreground(hwnd: int, foreground, seconds: float) -> bool:
    deadline = time.monotonic() + seconds
    while foreground() != hwnd:
        if time.monotonic() >= deadline:
            return False
        time.sleep(.02)
    return True


def pack_result(result: list) -> dict:
    summary = json.loads(result[0])
    screenshot = None
    if len(result) > 1:
        image = result[1]
        # FastMCP Image stores original bytes as .data.
        screenshot = 'data:image/png;base64,' + base64.b64encode(image.data).decode('ascii')
    return {'summary': summary, 'screenshot': screenshot}


class Engine:
    def __init__(self):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
        self.lock = threading.Lock()
        self.jobs = {}
        self.active = None

    def start(self, data):
        if not isinstance(data, dict) or set(data) - {'steps', 'mode', 'target_hwnd'}:
            raise ValueError('Invalid run request')
        steps = data.get('steps')
        if not isinstance(steps, list) or not 1 <= len(steps) <= 64:
            raise ValueError('Provide 1 to 64 steps')
        if any(not isinstance(s, dict) or set(s) - {'do', 'expect', 'risky', 'confirmed'} for s in steps):
            raise ValueError('Invalid step fields')
        parsed = [server.StepInput.model_validate(s) for s in steps]
        if any(s.risky and not s.confirmed for s in parsed):
            raise ValueError('Confirm each risky step before running')
        mode = data.get('mode', 'turbo')
        if mode not in ('turbo', 'human'):
            raise ValueError('Invalid mode')
        hwnd = data.get('target_hwnd')
        if type(hwnd) is not int or hwnd <= 0:
            raise ValueError('Select a target window')
        with self.lock:
            if self.active is not None:
                raise RuntimeError('Another execution is still running')
            job_id = secrets.token_urlsafe(18)
            job = {'id': job_id, 'status': 'queued', 'total': len(parsed),
                   'steps': [step.model_dump() for step in parsed], 'stop_requested': False}
            self.jobs[job_id] = job
            while len(self.jobs) > 30:
                del self.jobs[next(iter(self.jobs))]
            self.active = job_id
        try:
            asyncio.run_coroutine_threadsafe(self._run(job_id, parsed, mode, hwnd), self.loop)
        except Exception:
            with self.lock:
                self.active = None
                del self.jobs[job_id]
            raise
        return job_id

    async def _run(self, job_id, steps, mode, hwnd):
        try:
            with self.lock:
                job = self.jobs[job_id]
                if job['stop_requested']:
                    job['status'] = 'stopped'
                    return
                job['status'] = 'running'
            activate_target(hwnd)
            with self.lock:
                if job['stop_requested']:
                    job['status'] = 'stopped'
                    return
            job_started = time.monotonic()
            with self.lock:
                job['live'] = []
                job['current'] = None
                job['started_ms'] = 0

            def progress(event, i, res):
                with self.lock:
                    job['elapsed_ms'] = round((time.monotonic() - job_started) * 1000)
                    if event == 'start':
                        job['current'] = i
                    elif res is not None:
                        job['current'] = None
                        job['live'] = job['live'] + [{'i': i, 'status': res.status, 'action': res.action,
                                                      'ms': round(res.decide_ms + res.act_ms + res.verify_ms),
                                                      'verified': res.verified, 'note': res.note}]

            server.progress_callback.set(progress)
            result = await server.run_steps_tool(steps, mode, hwnd)
            packed = pack_result(result)
            with self.lock:
                job.update(packed)
                job['status'] = 'stopped' if job['stop_requested'] else ('completed' if packed['summary']['ok'] else 'handback')
        except Exception as exc:
            with self.lock:
                job['status'] = 'stopped' if job['stop_requested'] else 'error'
                job['error'] = str(exc)
        finally:
            with self.lock:
                if self.active == job_id:
                    self.active = None

    def stop(self, job_id=None):
        with self.lock:
            if job_id is not None and job_id != self.active:
                return {'active': False, 'stop_requested': False}
            job = self.jobs.get(self.active)
            if job is not None:
                job['stop_requested'] = True
            result = server.stop_tool()
            # Queue a job-bound stop on the loop to close the pre-start race.
            job_id = self.active
            def stop_if_current():
                with self.lock:
                    if self.active == job_id and job_id in self.jobs:
                        server.stop_tool()
            self.loop.call_soon_threadsafe(stop_if_current)
            return {'active': job is not None or result['active'], 'stop_requested': job is not None or result['stop_requested']}

    def get(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            return dict(job) if job else None

    def activity(self):
        with self.lock:
            kind = 'look' if self.active == 'look' else ('run' if self.active is not None else None)
            job = self.jobs.get(self.active)
            if job is None and self.jobs:
                job = self.jobs[next(reversed(self.jobs))]
            return {'busy': self.active is not None, 'kind': kind,
                    'job': dict(job) if job is not None else None}

    def look(self, hwnd):
        if type(hwnd) is not int or hwnd <= 0:
            raise ValueError('Select a target window')
        with self.lock:
            if self.active is not None:
                raise RuntimeError('Another execution is still running')
            # Reserve the engine while look activates and captures.
            self.active = 'look'
        try:
            async def capture():
                activate_target(hwnd)
                return server.look(hwnd)
            image = asyncio.run_coroutine_threadsafe(capture(), self.loop).result(timeout=30)
            return {'screenshot': 'data:image/png;base64,' + base64.b64encode(image.data).decode('ascii')}
        finally:
            with self.lock:
                self.active = None


class ProductServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, engine=None, token=None):
        super().__init__(address, Handler)
        self.engine = engine or Engine()
        self.token = token or secrets.token_urlsafe(32)


class Handler(BaseHTTPRequestHandler):
    server_version = 'CU-S1'
    def log_message(self, format, *args):
        pass

    def allowed(self, mutation=False):
        port = self.server.server_address[1]
        host = self.headers.get('Host', '')
        if host not in (f'127.0.0.1:{port}', f'localhost:{port}'):
            return False
        origin = self.headers.get('Origin')
        if origin and origin != f'http://{host}':
            return False
        if mutation and not secrets.compare_digest(self.headers.get('X-CU-S1-Token', ''), self.server.token):
            return False
        return True

    def reply(self, code, value, content_type='application/json; charset=utf-8'):
        body = json.dumps(value).encode('utf-8') if content_type.startswith('application/json') else value
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if not self.allowed():
            return self.reply(403, {'error': 'Forbidden'})
        path = urlsplit(self.path).path
        try:
            if path == '/':
                html = WEB.read_text(encoding='utf-8').replace('__TOKEN_JSON__', json.dumps(self.server.token))
                return self.reply(200, html.encode('utf-8'), 'text/html; charset=utf-8')
            if path == '/api/health':
                return self.reply(200, {'ok': True, 'product': 'cu-s1', 'api_version': 1})
            if path == '/api/windows':
                return self.reply(200, {'windows': server.windows()})
            if path == '/api/activity':
                return self.reply(200, self.server.engine.activity())
            if path == '/api/doctor':
                report, _ = diagnose()
                return self.reply(200, report)
            if path.startswith('/api/jobs/'):
                job = self.server.engine.get(path[len('/api/jobs/'):])
                return self.reply(200 if job else 404, job or {'error': 'Job not found'})
            self.reply(404, {'error': 'Not found'})
        except Exception as exc:
            self.reply(500, {'error': str(exc)})

    def do_POST(self):
        if not self.allowed(True):
            return self.reply(403, {'error': 'Forbidden'})
        try:
            length = int(self.headers.get('Content-Length', '-1'))
            if length < 0 or length > MAX_BODY:
                raise ValueError('Invalid request size')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('Expected a JSON object')
            path = urlsplit(self.path).path
            if path == '/api/run':
                return self.reply(202, {'job_id': self.server.engine.start(data)})
            if path == '/api/stop':
                return self.reply(200, self.server.engine.stop(data.get('job_id')))
            if path == '/api/look':
                return self.reply(200, self.server.engine.look(data.get('target_hwnd')))
            self.reply(404, {'error': 'Not found'})
        except (ValueError, TypeError) as exc:
            self.reply(400, {'error': str(exc)})
        except RuntimeError as exc:
            self.reply(409, {'error': str(exc)})
        except Exception as exc:
            self.reply(500, {'error': str(exc)})


def main():
    import msvcrt
    parser = argparse.ArgumentParser()
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    RUNTIME.mkdir(parents=True, exist_ok=True)
    lock = open(RUNTIME / 'service.lock', 'a+b')
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        if not args.no_browser:
            from .bridge import discover
            info = discover(wait=5)
            if info:
                webbrowser.open(f"http://127.0.0.1:{info['port']}/")
        return
    http = ProductServer(('127.0.0.1', 0))
    info = {'port': http.server_address[1], 'token': http.token, 'pid': os.getpid()}
    temporary = RUNTIME / f'service.{os.getpid()}.tmp'
    temporary.write_text(json.dumps(info), encoding='utf-8')
    os.replace(temporary, SERVICE_FILE)
    try:
        if not args.no_browser:
            webbrowser.open(f"http://127.0.0.1:{info['port']}/")
        http.serve_forever()
    finally:
        http.server_close()
        try:
            if json.loads(SERVICE_FILE.read_text(encoding='utf-8')).get('pid') == os.getpid():
                SERVICE_FILE.unlink()
        except (OSError, ValueError):
            pass
        lock.close()

if __name__ == '__main__':
    main()
