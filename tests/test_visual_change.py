import unittest

from PIL import Image, ImageDraw
from cu_s1.verify import changed_fraction, has_visible_change


class VisualChangeTests(unittest.TestCase):
    def test_small_check_mark_survives_thumbnail_averaging(self):
        before = Image.new('RGB', (1280, 900), 'white')
        after = before.copy()
        ImageDraw.Draw(after).line([(80, 80), (83, 84), (89, 76)], fill='black', width=2)
        self.assertLess(changed_fraction(before, after), .0002)
        self.assertTrue(has_visible_change(before, after))

    def test_identical_and_low_amplitude_noise_do_not_pass(self):
        before = Image.new('RGB', (640, 480), (128, 128, 128))
        self.assertFalse(has_visible_change(before, before.copy()))
        self.assertFalse(has_visible_change(before, Image.new('RGB', before.size, (130, 130, 130))))
        after = before.copy()
        after.putpixel((10, 10), (255, 255, 255))
        self.assertFalse(has_visible_change(before, after))

    def test_geometry_change_is_visible(self):
        self.assertTrue(has_visible_change(Image.new('RGB', (20, 20)), Image.new('RGB', (30, 20))))


if __name__ == '__main__':
    unittest.main()
