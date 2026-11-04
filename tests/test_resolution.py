import os
import unittest
from unittest.mock import patch
from PIL import Image
from cu_s1.screen import Frame


class ResolutionTests(unittest.TestCase):
    def setUp(self):
        self.frame = Frame(Image.new('RGB', (1920, 1080), 'navy'), 0, 0)

    def test_default_matches_original_resize(self):
        with patch.dict(os.environ, {}, clear=True):
            actual = self.frame.downscaled()
        expected = self.frame.image.resize((1280, 720), Image.LANCZOS)
        self.assertEqual(actual.tobytes(), expected.tobytes())
        self.assertEqual(actual.size, expected.size)

    def test_no_upscale_and_same_object(self):
        image = Image.new('RGB', (640, 480))
        with patch.dict(os.environ, {}, clear=True):
            self.assertIs(Frame(image, 0, 0).downscaled(), image)

    def test_env_resolution_and_aspect_ratio(self):
        with patch.dict(os.environ, {'CU_S1_MAX_SIDE': '1920'}):
            self.assertIs(self.frame.downscaled(), self.frame.image)
        with patch.dict(os.environ, {'CU_S1_MAX_SIDE': '960'}):
            self.assertEqual(self.frame.downscaled().size, (960, 540))
        tall = Frame(Image.new('RGB', (600, 1200)), 0, 0)
        with patch.dict(os.environ, {'CU_S1_MAX_SIDE': '600'}):
            self.assertEqual(tall.downscaled().size, (300, 600))

    def test_explicit_ignores_even_invalid_environment(self):
        with patch.dict(os.environ, {'CU_S1_MAX_SIDE': 'broken'}):
            self.assertEqual(self.frame.downscaled(1024).size, (1024, 576))

    def test_invalid_values_rejected_before_resize(self):
        for value in ('', 'abc', '320.0', '319', '1921', 'true'):
            with self.subTest(env=value), patch.dict(os.environ, {'CU_S1_MAX_SIDE': value}):
                with self.assertRaises(ValueError): self.frame.downscaled()
        for value in (True, False, 319, 1921, 1280.0, '1280'):
            with self.subTest(explicit=value):
                with self.assertRaises(ValueError): self.frame.downscaled(value)
        for value in (320, 1920):
            self.assertLessEqual(max(self.frame.downscaled(value).size), value)


if __name__ == '__main__':
    unittest.main()
