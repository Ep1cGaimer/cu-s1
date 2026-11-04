import contextlib
import io
import json
import unittest
from unittest.mock import Mock, patch

import httpx
from PIL import Image
from cu_s1 import doctor


def response(payload, status=200):
    return httpx.Response(status, json=payload, request=httpx.Request('GET', 'http://user:secret@localhost/private'))


class DoctorTests(unittest.TestCase):
    def setUp(self):
        self.vlm = Mock()
        self.vlm.model = 'local-model'
        self.vlm.openai = False
        self.vlm.client.get.return_value = response({'version': '0.9'})
        self.vlm.client.post.return_value = response({'capabilities': ['completion', 'vision']})
        self.factory = patch('cu_s1.doctor.Vlm', return_value=self.vlm)
        self.factory.start()
        self.addCleanup(self.factory.stop)

    def test_ollama_model_and_vision(self):
        report, status = doctor.diagnose('local-model')
        self.assertEqual(status, 0)
        self.assertEqual(report['vision'], 'supported')
        self.vlm.client.get.assert_called_once_with('/api/version')
        self.vlm.client.post.assert_called_once_with('/api/show', json={'model': 'local-model'})
        self.vlm._chat.assert_not_called()
        self.vlm.client.close.assert_called_once()

    def test_missing_backend_error_does_not_leak_url_or_credentials(self):
        self.vlm.client.get.side_effect = httpx.ConnectError('secret http://user:secret@localhost', request=httpx.Request('GET', 'http://localhost'))
        report, status = doctor.diagnose()
        self.assertEqual(status, 1)
        self.assertEqual(report['error'], 'backend: connection failed')
        self.assertNotIn('secret', json.dumps(report))
        self.vlm.client.post.assert_not_called()
        self.vlm.client.close.assert_called_once()

    def test_ollama_missing_model_and_nonvision(self):
        self.vlm.client.post.return_value = response({'error': 'secret'}, 404)
        report, status = doctor.diagnose()
        self.assertEqual(status, 1)
        self.assertEqual(report['error'], 'model: HTTP 404')
        self.assertFalse(report['model_available'])
        self.vlm.client.post.return_value = response({'capabilities': ['completion']})
        report, status = doctor.diagnose()
        self.assertEqual(status, 1)
        self.assertEqual(report['vision'], 'not supported')

    def test_nonvision_warmup_does_not_probe(self):
        self.vlm.client.post.return_value = response({'capabilities': ['completion']})
        report, status = doctor.diagnose(warmup=True)
        self.assertEqual(status, 1)
        self.assertEqual(report['vision'], 'not supported')
        self.vlm._chat.assert_not_called()

    def test_ollama_missing_capabilities_unknown(self):
        self.vlm.client.post.return_value = response({})
        report, status = doctor.diagnose()
        self.assertEqual(status, 0)
        self.assertEqual(report['vision'], 'unknown')

    def test_openai_model_listing_and_unknown_vision(self):
        self.vlm.openai = True
        self.vlm.client.get.return_value = response({'data': [{'id': 'local-model'}]})
        report, status = doctor.diagnose()
        self.assertEqual(status, 0)
        self.assertEqual(report['vision'], 'unknown')
        self.vlm.client.get.assert_called_once_with('/v1/models')
        self.vlm.client.get.return_value = response({'data': [{'id': 'other'}]})
        report, status = doctor.diagnose()
        self.assertEqual(status, 1)
        self.assertFalse(report['model_available'])

    def test_probe_uses_synthetic_image_and_reports_latency_not_accuracy(self):
        self.vlm._chat.return_value = ('white', 5)
        report, status = doctor.diagnose(warmup=True)
        self.assertEqual(status, 0)
        self.assertEqual(report['warmup'], 'nonempty response (accuracy not tested)')
        self.assertGreaterEqual(report['warmup_latency_ms'], 0)
        self.assertEqual(self.vlm._chat.call_args.kwargs['max_tokens'], 4)
        image = self.vlm._chat.call_args.args[1]
        self.assertIsInstance(image, Image.Image)
        self.assertEqual(image.size, (32, 32))
        self.assertEqual(image.getpixel((0, 0)), (255, 255, 255))
        self.vlm._chat.return_value = ('  ', 1)
        report, status = doctor.diagnose(warmup=True)
        self.assertEqual(status, 1)
        self.assertEqual(report['warmup'], 'empty response')

    def test_openai_probe_reports_acceptance_not_accuracy(self):
        self.vlm.openai = True
        self.vlm.client.get.return_value = response({'data': [{'id': 'local-model'}]})
        self.vlm._chat.return_value = ('answer', 1)
        report, status = doctor.diagnose(warmup=True)
        self.assertEqual(status, 0)
        self.assertEqual(report['vision'], 'image probe accepted (accuracy not tested)')

    def test_probe_failure_sanitized(self):
        self.vlm._chat.side_effect = RuntimeError('http://secret')
        report, status = doctor.diagnose(warmup=True)
        self.assertEqual(status, 1)
        self.assertEqual(report['warmup'], 'failed: request failed')
        self.vlm.client.close.assert_called_once()

    def test_cli_json_and_exit_code(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = doctor.main(['--model', 'local-model', '--json'])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out.getvalue())['model'], 'local-model')


if __name__ == '__main__':
    unittest.main()
