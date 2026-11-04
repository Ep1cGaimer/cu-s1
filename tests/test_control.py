import asyncio
import json
import threading
import unittest
from unittest.mock import Mock, patch

from cu_s1 import server
from cu_s1.runner import ChainResult


class ControlTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.started = threading.Event()
        self.release = threading.Event()
        self.target = Mock()
        self.target.guard.return_value = True
        self.target.capture.return_value = 'frame'
        self.kwargs = None
        def runner(steps, vlm, mode, **kwargs):
            self.kwargs = kwargs
            self.started.set()
            if not self.release.wait(5):
                raise RuntimeError('test timeout')
            return ChainResult(ok=True, completed=1, total=1)
        self.runner = Mock(side_effect=runner)
        self.patches = [patch('cu_s1.server.WindowTarget', return_value=self.target),
                        patch('cu_s1.server.run_steps', self.runner)]
        for p in self.patches: p.start()

    async def asyncTearDown(self):
        self.release.set()
        for _ in range(100):
            if not server.stop_tool()['active']:
                break
            await asyncio.sleep(.01)
        for p in reversed(self.patches): p.stop()
        self.assertFalse(server.stop_tool()['active'])

    async def wait_started(self):
        for _ in range(100):
            if self.started.is_set(): return
            await asyncio.sleep(.01)
        self.fail('worker did not start')

    def step(self):
        return [server.StepInput(do='safe step')]

    async def test_busy_stop_blocks_capture_and_input(self):
        task = asyncio.create_task(server.run_steps_tool(self.step(), target_hwnd=1))
        await self.wait_started()
        self.assertTrue(self.kwargs['input_guard']())
        with self.assertRaisesRegex(RuntimeError, 'still running'):
            await server.run_steps_tool(self.step(), target_hwnd=1)
        self.assertEqual(server.stop_tool(), {'active': True, 'stop_requested': True})
        self.assertFalse(self.kwargs['input_guard']())
        self.assertEqual(self.kwargs['input_guard'].failure_reason, 'execution stopped')
        with self.assertRaisesRegex(RuntimeError, 'stopped before capture'):
            self.kwargs['capture_fn']()
        self.target.capture.assert_not_called()
        self.release.set()
        result = await task
        self.assertTrue(json.loads(result[0])['ok'])
        self.assertFalse(server.stop_tool()['active'])

    async def test_guard_reason_propagates_and_clears(self):
        task = asyncio.create_task(server.run_steps_tool(self.step(), target_hwnd=1))
        await self.wait_started()
        guard = self.kwargs['input_guard']
        self.target.guard.return_value = False
        self.target.last_guard_failure = 'foreground changed'
        self.assertFalse(guard())
        self.assertEqual(guard.failure_reason, 'foreground changed')
        self.target.guard.return_value = True
        self.assertTrue(guard())
        self.assertIsNone(guard.failure_reason)
        self.release.set()
        await task

    async def test_cancellation_signals_but_keeps_busy_until_exit(self):
        task = asyncio.create_task(server.run_steps_tool(self.step(), target_hwnd=1))
        await self.wait_started()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertFalse(self.kwargs['input_guard']())
        with self.assertRaisesRegex(RuntimeError, 'still running'):
            await server.run_steps_tool(self.step(), target_hwnd=1)
        self.release.set()
        for _ in range(100):
            if not server.stop_tool()['active']: break
            await asyncio.sleep(.01)
        self.assertFalse(server.stop_tool()['active'])

    async def test_worker_exception_cleans_slot(self):
        self.runner.side_effect = RuntimeError('simulated failure')
        with self.assertRaisesRegex(RuntimeError, 'simulated failure'):
            await server.run_steps_tool(self.step(), target_hwnd=1)
        self.assertFalse(server.stop_tool()['active'])

    async def test_risk_step_passed_without_coercion(self):
        task = asyncio.create_task(server.run_steps_tool([server.StepInput(do='send', risky=True)], target_hwnd=1))
        await self.wait_started()
        self.assertTrue(self.runner.call_args.args[0][0].risky)
        self.assertFalse(self.runner.call_args.args[0][0].confirmed)
        self.release.set()
        await task


if __name__ == '__main__':
    unittest.main()
