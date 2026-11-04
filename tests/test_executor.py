import os
import unittest
from unittest.mock import patch, Mock

from PIL import Image
from cu_s1 import humanize
from cu_s1.runner import Step, run_steps
from cu_s1.screen import Frame
from cu_s1.vlm import Action, Vlm, parse_action


class ExecutorTests(unittest.TestCase):
    def setUp(self):
        self.frame = Frame(Image.new("RGB", (10, 10)), -10, 5)
        self.vlm = Mock()
        self.vlm.decide.return_value = Action("click", nx=.5, ny=.5)
        self.vlm.check.return_value = (False, 1)
        self.vlm.active_region.return_value = ((0, 0, 1, 1), 1)

    def run_chain(self, step, **kwargs):
        kwargs.setdefault('preflight', False)
        return run_steps([step], self.vlm, "turbo", capture_fn=lambda: self.frame,
                         stable_fn=lambda before: before, **kwargs)

    def test_parse_nested_strings_and_invalid_values(self):
        self.assertEqual(parse_action('```json\n{"action":"type","text":"{hi}"}\n```').text, '{hi}')
        for raw in ('{"action":"launch"}', '{"action":"click","point":["x",1]}',
                    '{"action":"click","point":[NaN,2]}', '{"action":"scroll","dy":0}',
                    '{"action":"scroll","dy":1.5}', '{"action":"key","keys":"f999"}',
                    '{"action":"type","text":42}', '{"action":"click"}'):
            with self.subTest(raw=raw):
                self.assertEqual(parse_action(raw).kind, 'invalid')

    def test_drag_parsing_and_strict_kind(self):
        action = parse_action('{"action":"drag","point":[0,1000],"to":[1000,0]}')
        self.assertEqual((action.nx, action.ny, action.dest_nx, action.dest_ny), (0, 1, 1, 0))
        for dest in ('null', '[0]', '[true,0]', '[NaN,0]', '[1001,0]'):
            self.assertEqual(parse_action('{"action":"drag","point":[0,0],"to":' + dest + '}').kind, 'invalid')
        self.assertEqual(parse_action('{"action":"drag","to":[0,0]}').kind, 'invalid')
        self.vlm.decide.return_value = Action('click', nx=.5, ny=.5)
        with patch('cu_s1.runner._execute') as execute:
            result = self.run_chain(Step('Drag the item to the box'))
        self.assertEqual(result.steps[0].status, 'handback')
        execute.assert_not_called()

    def test_drag_both_endpoints_must_be_inside_modal(self):
        self.vlm.active_region.return_value = ((.2, .2, .8, .8), 1)
        for coords in ((.1, .5, .5, .5), (.5, .5, .9, .5)):
            self.vlm.decide.return_value = Action('drag', nx=coords[0], ny=coords[1], dest_nx=coords[2], dest_ny=coords[3])
            with patch('cu_s1.runner._execute') as execute:
                result = self.run_chain(Step('Drag item to box'), preflight=True)
            self.assertEqual(result.steps[0].status, 'handback')
            execute.assert_not_called()
        self.vlm.target_visible.assert_not_called()

    def test_drag_presence_guard_and_coordinates(self):
        self.vlm.decide.return_value = Action('drag', nx=0, ny=0, dest_nx=1, dest_ny=1)
        self.vlm.target_visible.return_value = (False, 1)
        with patch('cu_s1.runner.humanize.drag') as drag:
            result = self.run_chain(Step('Drag item to box'), preflight=True)
            self.assertEqual(result.steps[0].status, 'handback')
            drag.assert_not_called()
            self.vlm.target_visible.return_value = (True, 1)
            self.run_chain(Step('Drag item to box'), preflight=True)
            drag.assert_called_once_with(-10, 5, -1, 14, 'turbo', guard=None)

    def test_no_replay_after_no_change_or_failed_expectation(self):
        with patch('cu_s1.runner._execute') as execute:
            result = self.run_chain(Step('click item'))
            self.assertEqual(result.steps[0].status, 'no_change')
            self.assertEqual(execute.call_count, 1)
            result = self.run_chain(Step('click item', expect='visible'))
            self.assertEqual(result.steps[0].status, 'expect_failed')
            self.assertEqual(execute.call_count, 2)

    def test_done_checks_expectation(self):
        self.vlm.decide.return_value = Action('done')
        result = self.run_chain(Step('find item', expect='visible'))
        self.assertEqual(result.steps[0].status, 'expect_failed')
        self.vlm.check.assert_called_once()

    def test_explicit_handback_never_injects_input(self):
        self.vlm.decide.return_value = parse_action('{"action":"handback","reason":"target absent"}')
        with patch('cu_s1.runner._execute') as execute:
            result = self.run_chain(Step('Click missing target'))
        self.assertEqual(result.steps[0].status, 'handback')
        execute.assert_not_called()

    def test_preflight_rejects_hallucinated_click(self):
        self.vlm.target_visible.return_value = (False, 7)
        with patch('cu_s1.runner._execute') as execute:
            result = self.run_chain(Step('Click missing target'), preflight=True)
        self.assertEqual(result.steps[0].status, 'handback')
        self.assertEqual(result.steps[0].verify_ms, 8)
        execute.assert_not_called()

    def test_click_command_cannot_substitute_scroll_or_typing(self):
        for action in (Action('scroll', nx=.5, ny=.5, dy=-6), Action('type', text='unrequested')):
            self.vlm.decide.return_value = action
            with patch('cu_s1.runner._execute') as execute:
                result = self.run_chain(Step('Click missing target'))
            self.assertEqual(result.steps[0].status, 'handback')
            execute.assert_not_called()

    def test_modal_boundary_rejects_background_pointer_before_input(self):
        self.vlm.active_region.return_value = ((.6, .6, .9, .9), 3)
        with patch('cu_s1.runner._execute') as execute:
            result = self.run_chain(Step('Click background button'), preflight=True)
        self.assertEqual(result.steps[0].status, 'handback')
        execute.assert_not_called()
        self.vlm.target_visible.assert_not_called()

    def test_unverified_done_hands_back(self):
        self.vlm.decide.return_value = Action('done')
        result = self.run_chain(Step('Click item'))
        self.assertEqual(result.steps[0].status, 'handback')

    def test_invalid_modal_bounds_are_uncertain(self):
        for raw in ('[]', '{"modal":"false"}', '{"modal":true,"box":[900,0,100,500]}',
                    '{"modal":true,"box":[0,0,1001,500]}', '{"modal":true,"box":[0,0,1.5,500]}'):
            client = Mock()
            client._chat.return_value = (raw, 2)
            self.assertEqual(Vlm.active_region(client, self.frame.image), (None, 2))

    def test_modal_bounds_are_normalized(self):
        client = Mock()
        client._chat.return_value = ('{"modal":true,"box":[100,200,800,900]}', 2)
        self.assertEqual(Vlm.active_region(client, self.frame.image), ((.1,.2,.8,.9), 2))

    def test_confirmation_does_not_coerce_strings(self):
        from cu_s1.server import StepInput
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            StepInput(do='send', risky=True, confirmed='false')

    def test_risky_step_never_calls_model_or_input(self):
        with patch('cu_s1.runner._execute') as execute:
            result = self.run_chain(Step('send', risky=True))
        self.assertEqual(result.steps[0].status, 'needs_confirmation')
        self.vlm.decide.assert_not_called()
        execute.assert_not_called()

    def test_window_geometry_change_rejects_input(self):
        from cu_s1.window import WindowTarget
        with patch('cu_s1.window.foreground', return_value=123), patch('cu_s1.window.u') as win:
            win.IsWindow.return_value=True
            win.IsWindowVisible.return_value=True
            win.IsIconic.return_value=False
            target=WindowTarget(123)
            target.observed_rect=(0,0,100,100)
            with patch.object(target,'rect',return_value=(10,0,100,100)):
                self.assertFalse(target.guard())

    def test_explicit_type_preserves_text_and_skips_decision(self):
        with patch('cu_s1.runner._execute') as execute:
            self.run_chain(Step('Type:  Hello {world}\n😀'))
        self.assertEqual(execute.call_args.args[0].text, ' Hello {world}\n😀')
        self.vlm.decide.assert_not_called()

    def test_explicit_press_and_guard(self):
        with patch('cu_s1.runner._execute') as execute:
            result = self.run_chain(Step('Press Ctrl+Enter'), input_guard=lambda: False)
        self.assertEqual(result.steps[0].status, 'error')
        execute.assert_not_called()
        self.vlm.decide.assert_not_called()

    def test_preexecute_guard_reason_is_reported(self):
        def guard():
            guard.failure_reason = 'target geometry changed'
            return False
        with patch('cu_s1.runner._execute') as execute:
            result = self.run_chain(Step('click item'), input_guard=guard)
        self.assertEqual(result.steps[0].note, 'target geometry changed')
        execute.assert_not_called()

    def test_exception_is_structured_and_no_replay(self):
        with patch('cu_s1.runner._execute', side_effect=OSError('partial input')) as execute:
            result = self.run_chain(Step('click item'))
        self.assertEqual(result.steps[0].status, 'error')
        self.assertIn('partial input', result.handback)
        execute.assert_called_once()
        result = run_steps([Step('x')], self.vlm, capture_fn=Mock(side_effect=OSError('capture')))
        self.assertEqual(result.steps[0].status, 'error')

    def test_screen_boundaries(self):
        self.assertEqual(self.frame.to_screen(1, 1), (-1, 14))
        with self.assertRaises(ValueError):
            self.frame.to_screen(1.1, 0)

    def test_unicode_surrogate_pair(self):
        with patch('cu_s1.humanize._send') as send:
            humanize.type_text('😀', 'turbo')
        self.assertEqual(send.call_count, 2)
        self.assertEqual([c.args[0].u.ki.wScan for c in send.call_args_list], [0xD83D, 0xDE00])

    def test_partial_chord_releases_modifiers(self):
        calls=[]
        def send(*inputs):
            calls.append(inputs[0].u.ki.dwFlags)
            if len(calls)==2: raise OSError('partial key injection')
        with patch('cu_s1.humanize._send', side_effect=send):
            with self.assertRaises(OSError): humanize.press('ctrl+a','turbo')
        self.assertEqual(calls[-2:],[humanize.KEYEVENTF_KEYUP,humanize.KEYEVENTF_KEYUP])

    def test_key_release_failure_is_reported(self):
        with patch('cu_s1.humanize._send', side_effect=[None,OSError('release failed')]):
            with self.assertRaisesRegex(OSError,'release failed'):
                humanize.press('a','turbo')

    def test_failed_mouse_down_still_releases(self):
        with patch('cu_s1.humanize.move_to'), patch('cu_s1.humanize._send', side_effect=[OSError('partial'),None]) as send:
            with self.assertRaises(OSError): humanize.click(5,5,mode='turbo')
        self.assertEqual(send.call_count,2)
        self.assertEqual(send.call_args.args[0].u.mi.dwFlags,humanize.MOUSEEVENTF_LEFTUP)

    def test_backend_environment(self):
        with patch.dict(os.environ, {'CU_S1_BACKEND': 'openai', 'CU_S1_BASE_URL': 'http://localhost:8080', 'CU_S1_MODEL': 'local'}, clear=True):
            client = Vlm()
            self.assertTrue(client.openai)
            self.assertEqual(client.model, 'local')
            client.client.close()
        with patch.dict(os.environ, {'CU_S1_BACKEND': 'ollama', 'CU_S1_BASE_URL': 'http://localhost:11434'}, clear=True):
            client = Vlm()
            self.assertFalse(client.openai)
            client.client.close()


if __name__ == '__main__':
    unittest.main()
