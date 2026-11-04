import http.client
import json
import threading
import tempfile
from pathlib import Path
import time
import unittest
from unittest import mock

from mcp.server.fastmcp import Image
from cu_s1 import app


class ProductTests(unittest.TestCase):
    def setUp(self):
        self.engine = app.Engine()
        self.http = app.ProductServer(('127.0.0.1', 0), self.engine, 'test-token')
        self.port = self.http.server_address[1]
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.http.shutdown()
        self.http.server_close()
        self.engine.loop.call_soon_threadsafe(self.engine.loop.stop)
        self.engine.thread.join(2)
        self.engine.loop.close()
        self.thread.join(2)

    def req(self, method, path, data=None, headers=None):
        conn = http.client.HTTPConnection('127.0.0.1', self.port, timeout=4)
        body = json.dumps(data) if data is not None else None
        conn.request(method, path, body=body, headers=headers or {})
        response = conn.getresponse()
        payload = response.read()
        conn.close()
        return response.status, payload

    def post(self, path, data, headers=None):
        return self.req('POST', path, data, headers or {'X-CU-S1-Token': 'test-token'})

    def test_host_origin_and_token_guards(self):
        code, body = self.req('GET', '/api/health')
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body), {'ok': True, 'product': 'cu-s1', 'api_version': 1})
        self.assertEqual(self.req('GET', '/', headers={'Host': 'evil.example'})[0], 403)
        self.assertEqual(self.req('GET', '/', headers={'Origin': 'https://evil.example'})[0], 403)
        self.assertEqual(self.post('/api/stop', {}, {'X-CU-S1-Token': 'wrong'})[0], 403)
        self.assertEqual(self.post('/api/stop', {}, {'X-CU-S1-Token': 'test-token', 'Origin': 'https://evil.example'})[0], 403)
        self.assertEqual(self.req('GET', '/.runtime/service.json')[0], 404)

    def test_validation_and_risky_confirmation(self):
        for data in ({'steps': [], 'target_hwnd': 1},
                     {'steps': [{'do': 'Click', 'risky': True}], 'target_hwnd': 1},
                     {'steps': [{'do': 'Click', 'risky': 'true'}], 'target_hwnd': 1},
                     {'steps': [{'do': 'Click'}], 'target_hwnd': True}):
            self.assertEqual(self.post('/api/run', data)[0], 400)

    def test_job_result_and_screenshot_are_actual_tool_output(self):
        async def run(*args):
            return [json.dumps({'ok': True, 'completed': 1, 'total': 1}), Image(data=b'png bytes', format='png')]
        with mock.patch.object(app, 'activate_target') as activate, mock.patch.object(app.server, 'run_steps_tool', run):
            code, body = self.post('/api/run', {'steps': [{'do': 'Click'}], 'target_hwnd': 12})
            self.assertEqual(code, 202)
            job_id = json.loads(body)['job_id']
            for _ in range(100):
                job = json.loads(self.req('GET', '/api/jobs/' + job_id)[1])
                if job['status'] not in ('queued', 'running'):
                    break
                time.sleep(.01)
            self.assertEqual(job['status'], 'completed')
            self.assertEqual(job['summary']['completed'], 1)
            self.assertEqual(job['screenshot'], 'data:image/png;base64,cG5nIGJ5dGVz')
            latest = json.loads(self.req('GET', '/api/activity')[1])
            self.assertFalse(latest['busy'])
            self.assertEqual(latest['job']['steps'][0]['do'], 'Click')
            self.assertEqual(latest['job']['screenshot'], job['screenshot'])
            activate.assert_called_once_with(12)

    def test_stop_and_concurrent_rejection(self):
        started = threading.Event()
        release = threading.Event()
        async def run(*args):
            started.set()
            await __import__('asyncio').to_thread(release.wait, 3)
            return [json.dumps({'ok': False, 'completed': 0, 'total': 1})]
        with mock.patch.object(app, 'activate_target'), mock.patch.object(app.server, 'run_steps_tool', run), mock.patch.object(app.server, 'stop_tool', return_value={'active': True, 'stop_requested': True}) as stop:
            self.assertEqual(json.loads(self.req('GET', '/api/activity')[1]), {'busy': False, 'kind': None, 'job': None})
            data = {'steps': [{'do': 'Click', 'expect': 'Done'}], 'target_hwnd': 12}
            code, body = self.post('/api/run', data)
            self.assertEqual(code, 202)
            self.assertTrue(started.wait(2))
            job_id = json.loads(body)['job_id']
            activity = json.loads(self.req('GET', '/api/activity')[1])
            self.assertTrue(activity['busy'])
            self.assertEqual(activity['kind'], 'run')
            self.assertEqual(activity['job']['id'], job_id)
            self.assertEqual(activity['job']['steps'][0]['expect'], 'Done')
            self.assertEqual(self.post('/api/run', data)[0], 409)
            self.assertFalse(json.loads(self.post('/api/stop', {'job_id': 'other-job'})[1])['stop_requested'])
            self.assertTrue(json.loads(self.post('/api/stop', {'job_id': job_id})[1])['stop_requested'])
            self.assertTrue(json.loads(self.req('GET', '/api/activity')[1])['job']['stop_requested'])
            release.set()
            job_id = json.loads(body)['job_id']
            for _ in range(100):
                job = self.engine.get(job_id)
                if job['status'] == 'stopped':
                    break
                time.sleep(.01)
            self.assertEqual(job['status'], 'stopped')
            latest = json.loads(self.req('GET', '/api/activity')[1])
            self.assertFalse(latest['busy'])
            self.assertEqual(latest['job']['id'], job_id)
            self.assertEqual(latest['job']['status'], 'stopped')
            self.assertEqual(latest['job']['summary']['completed'], 0)
            with self.engine.lock:
                self.engine.active = 'look'
            during_look = json.loads(self.req('GET', '/api/activity')[1])
            self.assertTrue(during_look['busy'])
            self.assertEqual(during_look['kind'], 'look')
            self.assertEqual(during_look['job']['id'], job_id)
            with self.engine.lock:
                self.engine.active = None
            self.assertTrue(stop.called)



class RuntimeLocationTests(unittest.TestCase):
    def test_editable_installed_and_explicit_locations(self):
        from cu_s1.paths import runtime_location
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            workspace = base / 'workspace'
            workspace.mkdir()
            (workspace / 'pyproject.toml').touch()
            env = {'LOCALAPPDATA': str(base / 'local')}
            self.assertEqual(runtime_location(workspace, env), (workspace / '.runtime', workspace))
            installed = base / 'site-packages'
            installed.mkdir()
            home = base / 'local' / 'cu-s1'
            self.assertEqual(runtime_location(installed, env), (home, home))
            explicit = base / 'custom'
            self.assertEqual(runtime_location(installed, {**env, 'CU_S1_HOME': str(explicit)}), (explicit, explicit))
            self.assertFalse(home.exists())
            self.assertFalse(explicit.exists())

    def test_discovery_rejects_unrelated_health_endpoint(self):
        from cu_s1 import bridge
        with tempfile.TemporaryDirectory() as tmp:
            service = Path(tmp) / 'service.json'
            service.write_text(json.dumps({'port': 1234, 'token': 'test'}), encoding='utf-8')
            with mock.patch.object(bridge, 'SERVICE_FILE', service), mock.patch.object(bridge, 'request', return_value={'ok': True}):
                self.assertIsNone(bridge.discover())
            with mock.patch.object(bridge, 'SERVICE_FILE', service), mock.patch.object(bridge, 'request', return_value={'ok': True, 'product': 'cu-s1', 'api_version': 1}):
                self.assertEqual(bridge.discover()['port'], 1234)


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_call_stops_after_delayed_submission(self):
        import asyncio
        import anyio
        from cu_s1 import bridge
        submitted = threading.Event()
        release = threading.Event()
        stopped = threading.Event()
        calls = []
        def request(info, path, data=None, timeout=10):
            calls.append((path, data))
            if path == '/api/run':
                submitted.set()
                release.wait(2)
                return {'job_id': 'job'}
            if path == '/api/stop':
                stopped.set()
                return {'stop_requested': True}
            return {'status': 'running'}
        with mock.patch.object(bridge, 'service', return_value={'port': 1, 'token': 'test'}), mock.patch.object(bridge, 'request', request):
            scopes = []
            async def caller():
                with anyio.CancelScope() as scope:
                    scopes.append(scope)
                    await bridge.run_steps([app.server.StepInput(do='Click')], target_hwnd=1)
            task = asyncio.create_task(caller())
            self.assertTrue(await asyncio.to_thread(submitted.wait, 2))
            scopes[0].cancel()
            await asyncio.wait_for(task, 1)
            self.assertFalse(stopped.is_set())
            self.assertTrue(bridge._cleanup_tasks)
            scopes[0].cancel()  # Repeated scope cancellation must not cancel cleanup.
            release.set()
            self.assertTrue(await asyncio.to_thread(stopped.wait, 2))
            for _ in range(100):
                if not bridge._cleanup_tasks:
                    break
                await asyncio.sleep(.01)
            self.assertFalse(bridge._cleanup_tasks)
            self.assertEqual([c[0] for c in calls], ['/api/run', '/api/stop'])
            self.assertEqual(calls[-1][1], {'job_id': 'job'})

class ActivationTests(unittest.TestCase):
    def test_already_foreground_needs_no_activation_call(self):
        with mock.patch.object(app.server, 'windows', return_value=[{'hwnd': 12}]), \
             mock.patch('cu_s1.window.foreground', return_value=12), \
             mock.patch.object(app.ctypes, 'windll') as dll:
            dll.user32.IsIconic.return_value = False
            app.activate_target(12)
            dll.user32.SetForegroundWindow.assert_not_called()

    def test_observed_foreground_is_success_even_if_api_returns_zero(self):
        with mock.patch.object(app.server, 'windows', return_value=[{'hwnd': 12}]), \
             mock.patch('cu_s1.window.foreground', side_effect=[1, 1, 12]), \
             mock.patch.object(app.ctypes, 'windll') as dll:
            dll.user32.IsIconic.return_value = False
            dll.kernel32.GetCurrentThreadId.return_value = 10
            dll.user32.GetWindowThreadProcessId.return_value = 20
            dll.user32.AttachThreadInput.return_value = 1
            dll.user32.SetForegroundWindow.return_value = 0
            app.activate_target(12)
            self.assertEqual(dll.user32.AttachThreadInput.call_args_list, [mock.call(10, 20, True), mock.call(10, 20, False)])

    def test_foreground_failure_rejected_and_attachment_released(self):
        with mock.patch.object(app.server, 'windows', return_value=[{'hwnd': 12}]), \
             mock.patch('cu_s1.window.foreground', return_value=1), \
             mock.patch.object(app.ctypes, 'windll') as dll, \
             mock.patch('cu_s1.app.time.monotonic', side_effect=[0, 1, 0, 1]):
            dll.user32.IsIconic.return_value = False
            dll.kernel32.GetCurrentThreadId.return_value = 10
            dll.user32.GetWindowThreadProcessId.return_value = 20
            dll.user32.AttachThreadInput.return_value = 1
            with self.assertRaisesRegex(RuntimeError, 'Could not activate'):
                app.activate_target(12)
            self.assertEqual(dll.user32.AttachThreadInput.call_args_list, [mock.call(10, 20, True), mock.call(10, 20, False)])
            # One Alt tap (down, up) is the only fallback input before failing.
            self.assertEqual(dll.user32.keybd_event.call_args_list, [mock.call(0x12, 0, 0, 0), mock.call(0x12, 0, 2, 0)])
            self.assertEqual(dll.user32.SetForegroundWindow.call_count, 2)


if __name__ == '__main__':
    unittest.main()
