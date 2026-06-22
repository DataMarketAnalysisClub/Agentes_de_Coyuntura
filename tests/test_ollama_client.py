from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from services.ai.ollama_client import OllamaCloudClient, OllamaCloudError


def _make_settings(
    ai_enabled: bool = True,
    ai_dry_run: bool = True,
    ollama_api_key: str = "test-key",
    ollama_model: str = "gpt-oss:120b",
) -> Settings:
    return Settings(
        ai_enabled=ai_enabled,
        ai_dry_run=ai_dry_run,
        ollama_api_key=ollama_api_key,
        ollama_model=ollama_model,
        ollama_base_url="https://ollama.com",
        ollama_timeout_seconds=5.0,
        ollama_temperature=0.2,
        ollama_max_retries=1,
    )


class TestOllamaCloudClient:
    def test_disabled_raises(self) -> None:
        settings = _make_settings(ai_enabled=False)
        client = OllamaCloudClient(settings=settings)
        with pytest.raises(OllamaCloudError, match="disabled"):
            client.chat_json("sys", "user")

    def test_dry_run_returns_stub(self) -> None:
        settings = _make_settings(ai_enabled=True, ai_dry_run=True)
        client = OllamaCloudClient(settings=settings)
        result = client.chat_json("sys", "user")
        assert "status" in result
        assert "dry-run" in result.lower()

    def test_dry_run_does_not_call_network(self) -> None:
        settings = _make_settings(ai_enabled=True, ai_dry_run=True)
        client = OllamaCloudClient(settings=settings)
        with patch.object(client, "_call_api") as mock_api:
            client.chat_json("sys", "user")
            mock_api.assert_not_called()

    def test_missing_api_key_raises(self) -> None:
        settings = _make_settings(
            ai_enabled=True,
            ai_dry_run=False,
            ollama_api_key="",
        )
        client = OllamaCloudClient(settings=settings)
        with pytest.raises(OllamaCloudError, match="OLLAMA_API_KEY"):
            client.chat_json("sys", "user")

    def test_missing_model_raises(self) -> None:
        settings = _make_settings(
            ai_enabled=True,
            ai_dry_run=False,
            ollama_model="",
        )
        client = OllamaCloudClient(settings=settings)
        with pytest.raises(OllamaCloudError, match="OLLAMA_MODEL"):
            client.chat_json("sys", "user")

    def test_call_api_invokes_http_client(self) -> None:
        settings = _make_settings(ai_enabled=True, ai_dry_run=False)
        client = OllamaCloudClient(settings=settings)
        mock_http = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = {"message": {"content": '{"status":"ok"}'}}
        mock_http.post.return_value = mock_response
        client._http = mock_http
        result = client.chat_json("sys", "user")
        assert mock_http.post.called
        assert "status" in result
