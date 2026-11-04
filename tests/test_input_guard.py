import unittest
from unittest.mock import Mock, patch
from cu_s1 import humanize as h


class InputGuardTests(unittest.TestCase):
    def test_partial_typing_stops(self):
        with patch.object(h, '_send') as send:
            with self.assertRaisesRegex(RuntimeError, 'guard'):
                h.type_text('abc', 'turbo', guard=Mock(side_effect=[True, False]))
        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.args[0].u.ki.wScan, ord('a'))
        self.assertTrue(send.call_args.args[1].u.ki.dwFlags & h.KEYEVENTF_KEYUP)

    def test_partial_chord_releases_modifier_without_guard(self):
        with patch.object(h, '_send') as send:
            with self.assertRaisesRegex(RuntimeError, 'guard'):
                h.press('ctrl+a', 'turbo', guard=Mock(side_effect=[True, False]))
        self.assertEqual(send.call_count, 2)
        self.assertEqual(send.call_args_list[0].args[0].u.ki.wVk, 0x11)
        self.assertEqual(send.call_args_list[1].args[0].u.ki.dwFlags, h.KEYEVENTF_KEYUP)

    def test_scroll_stops_after_first_notch(self):
        with patch.object(h, '_set_cursor_pos'), patch.object(h, '_send') as send:
            with self.assertRaisesRegex(RuntimeError, 'guard'):
                h.scroll(2, 3, -5, 'turbo', guard=Mock(side_effect=[True, True, False]))
        self.assertEqual(send.call_count, 1)
        self.assertEqual(send.call_args.args[0].u.mi.dwFlags, h.MOUSEEVENTF_WHEEL)

    def test_motion_stops_mid_path(self):
        with patch.object(h, 'cursor_pos', return_value=(0, 0)), patch.object(h, '_set_cursor_pos') as move, patch.object(h.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'guard'):
                h.move_to(100, 0, 'human', guard=Mock(side_effect=[True, False]))
        self.assertEqual(move.call_count, 1)

    def test_double_click_stops_after_first_and_releases(self):
        with patch.object(h, '_set_cursor_pos'), patch.object(h, '_send') as send, patch.object(h.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'guard'):
                h.click(2, 3, double=True, mode='turbo', guard=Mock(side_effect=[True, True, False]))
        self.assertEqual([c.args[0].u.mi.dwFlags for c in send.call_args_list], [h.MOUSEEVENTF_LEFTDOWN, h.MOUSEEVENTF_LEFTUP])

    def test_drag_stop_releases_after_partial_motion(self):
        with patch.object(h, '_set_cursor_pos') as move, patch.object(h, '_send') as send, patch.object(h.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'guard'):
                h.drag(0, 0, 100, 0, 'turbo', guard=Mock(side_effect=[True, True, True, False]))
        self.assertEqual(move.call_count, 2)
        self.assertEqual([c.args[0].u.mi.dwFlags for c in send.call_args_list], [h.MOUSEEVENTF_LEFTDOWN, h.MOUSEEVENTF_LEFTUP])

    def test_stop_reason_propagates_and_drag_releases(self):
        calls = 0
        def guard():
            nonlocal calls
            calls += 1
            if calls == 4:
                guard.failure_reason = 'execution stopped'
                return False
            return True
        with patch.object(h, '_set_cursor_pos'), patch.object(h, '_send') as send, patch.object(h.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'execution stopped'):
                h.drag(0, 0, 100, 0, 'turbo', guard=guard)
        self.assertEqual(send.call_args.args[0].u.mi.dwFlags, h.MOUSEEVENTF_LEFTUP)

    def test_drag_failed_down_attempts_release(self):
        with patch.object(h, '_set_cursor_pos'), patch.object(h, '_send', side_effect=[OSError('partial'), None]) as send:
            with self.assertRaisesRegex(OSError, 'partial'):
                h.drag(0, 0, 100, 0, 'turbo')
        self.assertEqual(send.call_args.args[0].u.mi.dwFlags, h.MOUSEEVENTF_LEFTUP)

    def test_newline_propagates_guard(self):
        with patch.object(h, '_send') as send:
            with self.assertRaisesRegex(RuntimeError, 'guard'):
                h.type_text('a\nb', 'turbo', guard=Mock(side_effect=[True, False]))
        self.assertEqual(send.call_count, 1)

    def test_partial_unicode_batch_attempts_release(self):
        with patch.object(h, '_send', side_effect=[OSError('partial'), None]) as send:
            with self.assertRaisesRegex(OSError, 'partial'):
                h.type_text('a', 'turbo', guard=lambda: True)
        self.assertEqual(send.call_count, 2)
        self.assertEqual(send.call_args.args[0].u.ki.dwFlags, h.KEYEVENTF_UNICODE | h.KEYEVENTF_KEYUP)


if __name__ == '__main__':
    unittest.main()
