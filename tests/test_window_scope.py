import unittest
from unittest.mock import Mock, patch

from PIL import Image
from cu_s1.screen import Frame, capture
from cu_s1.window import WindowTarget


class ScreenCaptureTests(unittest.TestCase):
    def test_virtual_capture_selects_all_and_primary_default_remains(self):
        virtual = {'left': -2, 'top': -1, 'width': 4, 'height': 2}
        primary = {'left': 0, 'top': 0, 'width': 2, 'height': 1}
        secondary = {'left': -2, 'top': -1, 'width': 2, 'height': 2}
        grabber = Mock()
        grabber.monitors = [virtual, primary, secondary]
        grabber.grab.side_effect = lambda m: Mock(size=(m['width'], m['height']),
                                                  bgra=b'\x00\x00\x00\xff' * m['width'] * m['height'])
        context = Mock()
        context.__enter__ = Mock(return_value=grabber)
        context.__exit__ = Mock(return_value=False)
        with patch('cu_s1.screen.mss.mss', return_value=context):
            full = capture(0)
            self.assertEqual((full.left, full.top, full.size), (-2, -1, (4, 2)))
            self.assertEqual(full.monitors, ((0, 0, 2, 1), (-2, -1, 2, 2)))
            first = capture()
            self.assertEqual((first.left, first.top, first.size), (0, 0, (2, 1)))
            self.assertEqual(first.monitors, ((0, 0, 2, 1),))



class WindowScopeTests(unittest.TestCase):
    def setUp(self):
        self.fg = 100
        self.pids = {100: 7, 200: 7, 201: 7, 300: 7, 400: 9}
        self.owners = {200: 100, 201: 200, 300: 0, 400: 100}
        self.rects = {100: (10, 10, 200, 150), 200: (30, 30, 100, 80),
                      201: (40, 40, 90, 70), 300: (20, 20, 90, 70), 400: (20, 20, 90, 70)}
        self.patchers = [patch('cu_s1.window.u'),
                         patch('cu_s1.window.foreground', side_effect=lambda: self.fg),
                         patch('cu_s1.window._process_id', side_effect=lambda h: self.pids.get(h, 0)),
                         patch('cu_s1.window.capture', return_value=Frame(Image.new('RGB', (800, 600)), 0, 0))]
        self.win = self.patchers[0].start()
        for p in self.patchers[1:]: p.start()
        self.addCleanup(lambda: [p.stop() for p in reversed(self.patchers)])
        self.win.IsWindow.side_effect = lambda h: h in self.pids
        self.win.IsWindowVisible.return_value = True
        self.win.IsIconic.return_value = False
        self.win.GetWindow.side_effect = lambda h, flag: self.owners.get(h, 0)
        self.target = WindowTarget(100)
        self.rect_patch = patch.object(self.target, 'rect', side_effect=lambda h=None: self.rects[h or 100])
        self.rect_patch.start()
        self.addCleanup(self.rect_patch.stop)

    def test_guard_diagnostics_distinguish_and_clear_failures(self):
        self.assertFalse(self.target.guard())
        self.assertEqual(self.target.last_guard_failure, 'no observed capture')
        self.target.capture()
        self.fg = 200
        self.assertFalse(self.target.guard())
        self.assertEqual(self.target.last_guard_failure, 'foreground changed')
        self.fg = 100
        self.rects[100] = (11, 10, 200, 150)
        self.assertFalse(self.target.guard())
        self.assertEqual(self.target.last_guard_failure, 'target geometry changed')
        with patch.object(self.target, 'rect', side_effect=OSError('details must not leak')):
            self.assertFalse(self.target.guard())
            self.assertEqual(self.target.last_guard_failure, 'target geometry unavailable')
        self.rects[100] = (10, 10, 200, 150)
        self.win.IsIconic.return_value = True
        self.assertFalse(self.target.guard())
        self.assertEqual(self.target.last_guard_failure, 'target ownership or visibility changed')
        self.win.IsIconic.return_value = False
        self.assertTrue(self.target.guard())
        self.assertIsNone(self.target.last_guard_failure)

    def test_owned_same_process_modal_and_nested_owner(self):
        for hwnd in (200, 201):
            self.fg = hwnd
            frame = self.target.capture()
            self.assertEqual((frame.left, frame.top), self.rects[hwnd][:2])
            self.assertEqual(self.target.observed_hwnd, hwnd)
            self.assertTrue(self.target.guard())

    def test_reject_unowned_and_different_process(self):
        for hwnd in (300, 400, 999):
            with self.subTest(hwnd=hwnd):
                self.fg = hwnd
                with self.assertRaises(RuntimeError): self.target.capture()

    def test_modal_transition_invalidates_guard_until_recaptured(self):
        self.target.capture()
        self.assertTrue(self.target.guard())
        self.fg = 200
        self.assertFalse(self.target.guard())
        self.target.capture()
        self.assertTrue(self.target.guard())
        self.fg = 100
        self.assertFalse(self.target.guard())
        self.target.capture()
        self.assertTrue(self.target.guard())

    def test_geometry_change_and_outside_primary_rejected(self):
        self.target.capture()
        self.rects[100] = (11, 10, 200, 150)
        self.assertFalse(self.target.guard())
        self.target.capture()
        self.assertTrue(self.target.guard())
        self.rects[100] = (-1, 10, 200, 150)
        with self.assertRaises(RuntimeError): self.target.capture()

    def test_negative_origin_monitor_crop_and_global_coordinates(self):
        # Virtual desktop spans two monitors, left monitor begins at negative x/y.
        image = Image.new('RGB', (1600, 700), 'black')
        image.paste('red', (0, 0, 800, 600))
        image.paste('blue', (800, 100, 1600, 700))
        frame = Frame(image, -800, -100, ((-800, -100, 800, 600), (0, 0, 800, 600)))
        self.rects[100] = (-700, -50, 200, 150)
        with patch('cu_s1.window.capture', return_value=frame) as capture:
            actual = self.target.capture()
        capture.assert_called_once_with(0)
        self.assertEqual(actual.image.getpixel((0, 0)), (255, 0, 0))
        self.assertEqual(actual.to_screen(0, 0), (-700, -50))
        self.assertEqual(actual.to_screen(1, 1), (-501, 99))
        self.assertTrue(self.target.guard())

    def test_monitor_union_allows_spanning_and_rejects_gaps(self):
        frame = Frame(Image.new('RGB', (1600, 700)), -800, -100,
                      ((-800, -100, 800, 600), (0, 0, 800, 600)))
        with patch('cu_s1.window.capture', return_value=frame):
            self.rects[100] = (-100, 50, 200, 150)  # spans both monitors
            self.target.capture()
            self.assertTrue(self.target.guard())
            self.rects[100] = (-100, -50, 200, 150)  # top right lies in display gap
            with self.assertRaisesRegex(RuntimeError, 'connected displays'):
                self.target.capture()
            self.rects[100] = (700, 0, 200, 150)  # extends beyond virtual edge
            with self.assertRaisesRegex(RuntimeError, 'connected displays'):
                self.target.capture()

    def test_visibility_pid_reuse_and_owner_cycle_rejected(self):
        self.target.capture()
        self.win.IsIconic.return_value = True
        self.assertFalse(self.target.guard())
        self.win.IsIconic.return_value = False
        self.pids[100] = 8
        self.assertFalse(self.target.guard())
        self.pids[100] = 7
        self.owners[200] = 201
        self.owners[201] = 200
        self.fg = 200
        with self.assertRaises(RuntimeError): self.target.capture()

    def test_capture_changed_midflight_does_not_authorize_new_window(self):
        self.target.capture()
        with patch('cu_s1.window.capture', side_effect=lambda *args: self.change_foreground()):
            with self.assertRaises(RuntimeError): self.target.capture()
        self.assertFalse(self.target.guard())
        self.assertEqual(self.target.observed_hwnd, 100)

    def change_foreground(self):
        self.fg = 200
        return Frame(Image.new('RGB', (800, 600)), 0, 0)


if __name__ == '__main__':
    unittest.main()
