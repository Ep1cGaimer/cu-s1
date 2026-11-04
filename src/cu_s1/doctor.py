"""Diagnose the configured local vision backend without reading the desktop.

Run: python -m cu_s1.doctor [--model NAME] [--warmup] [--json]
"""
from __future__ import annotations

import argparse
import json
import time
from typing import Any

import httpx
from PIL import Image

from .vlm import Vlm


def _error(exc: Exception) -> str:
    """Keep endpoint URLs, response bodies and credentials out of diagnostics."""
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    if isinstance(exc, httpx.TimeoutException):
        return "request timed out"
    if isinstance(exc, httpx.RequestError):
        return "connection failed"
    if isinstance(exc, (KeyError, TypeError, ValueError)):
        return "invalid backend response"
    return "request failed"


def diagnose(model: str | None = None, warmup: bool = False) -> tuple[dict[str, Any], int]:
    report: dict[str, Any] = {
        "backend": None, "model": None, "backend_available": False,
        "model_available": False, "vision": "unknown", "warmup": "not requested",
    }
    try:
        vlm = Vlm(model=model)
    except Exception as exc:
        report["error"] = f"configuration: {_error(exc)}"
        return report, 1
    try:
        report["backend"] = "openai-compatible" if vlm.openai else "ollama"
        report["model"] = vlm.model
        if vlm.openai:
            try:
                response = vlm.client.get('/v1/models')
                response.raise_for_status()
                data = response.json()
                models = data['data']
                if not isinstance(models, list) or any(not isinstance(item, dict) for item in models):
                    raise ValueError('invalid models list')
                report["backend_available"] = True
                report["model_available"] = any(item.get('id') == vlm.model for item in models)
            except Exception as exc:
                report['error'] = f"backend: {_error(exc)}"
                return report, 1
        else:
            try:
                response = vlm.client.get('/api/version')
                response.raise_for_status()
                data = response.json()
                if not isinstance(data.get('version'), str):
                    raise ValueError('invalid version')
                report['backend_available'] = True
                report['backend_version'] = data['version']
            except Exception as exc:
                report['error'] = f"backend: {_error(exc)}"
                return report, 1
            try:
                response = vlm.client.post('/api/show', json={'model': vlm.model})
                response.raise_for_status()
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError('invalid model response')
                report['model_available'] = True
                capabilities = data.get('capabilities')
                if isinstance(capabilities, list) and all(isinstance(x, str) for x in capabilities):
                    report['vision'] = 'supported' if 'vision' in capabilities else 'not supported'
            except httpx.HTTPStatusError as exc:
                report['error'] = f"model: {_error(exc)}"
                return report, 1
            except Exception as exc:
                report['error'] = f"model: {_error(exc)}"
                return report, 1
        if not report['model_available']:
            report['error'] = 'configured model not found'
            return report, 1
        if report['vision'] == 'not supported':
            report['error'] = 'model does not advertise vision capability'
            return report, 1
        if warmup:
            try:
                # Synthetic RGB image; no screenshot or computer input.
                image = Image.new('RGB', (32, 32), 'white')
                start = time.perf_counter()
                text, _ = vlm._chat('Describe this image in one short sentence.', image, max_tokens=4)
                report['warmup_latency_ms'] = round((time.perf_counter() - start) * 1000, 1)
                if not isinstance(text, str) or not text.strip():
                    report['warmup'] = 'empty response'
                    return report, 1
                report['warmup'] = 'nonempty response (accuracy not tested)'
                if report['vision'] == 'unknown':
                    report['vision'] = 'image probe accepted (accuracy not tested)'
            except Exception as exc:
                report['warmup'] = f"failed: {_error(exc)}"
                return report, 1
        return report, 0
    finally:
        vlm.client.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', default=None, help='Model name; defaults to CU_S1_MODEL or the Vlm default')
    parser.add_argument('--warmup', action='store_true', help='Send a synthetic image and measure response latency')
    parser.add_argument('--json', action='store_true', help='Print JSON instead of human-readable output')
    args = parser.parse_args(argv)
    report, code = diagnose(args.model, args.warmup)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for key, value in report.items():
            print(f"{key.replace('_', ' ')}: {value}")
    return code


if __name__ == '__main__':
    raise SystemExit(main())
