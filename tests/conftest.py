"""Pytest configuration: prevent accidental Ollama Cloud calls in tests.

The project loads settings from `.env`, which can have AI_ENABLED=true and
a real OLLAMA_API_KEY. Tests should never hit the real API. This conftest
patches OllamaCloudClient in all AI modules so any test that creates a client
gets a mock that is disabled and returns dry-run stubs.

Tests that want to exercise the Ollama path (e.g. test_ollama_client.py) can
mark themselves with @pytest.mark.allow_ollama_calls.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

_OLLAMA_TARGETS = (
    "services.ai.macro_router.OllamaCloudClient",
    "services.ai.topic_router.OllamaCloudClient",
    "services.ai.pipeline.OllamaCloudClient",
    "services.ai.editorial_writer.OllamaCloudClient",
    "services.ai.smoke_test.OllamaCloudClient",
)


@pytest.fixture(autouse=True)
def _disable_ollama_calls(request):
    if "allow_ollama_calls" in request.keywords:
        yield
        return
    from app.config import Settings

    settings = Settings(
        ai_enabled=False,
        ai_dry_run=True,
        ollama_api_key="test-key",
        ollama_model="gpt-oss:120b",
        ollama_base_url="https://ollama.com",
        ollama_timeout_seconds=5.0,
        ollama_temperature=0.2,
        ollama_max_retries=1,
    )
    patches = [patch(target) for target in _OLLAMA_TARGETS]
    mocks = [p.start() for p in patches]
    for mock in mocks:
        mock.return_value.settings = settings
        mock.return_value.is_enabled.return_value = False
        mock.return_value.is_dry_run.return_value = True
    try:
        yield
    finally:
        for p in patches:
            p.stop()
