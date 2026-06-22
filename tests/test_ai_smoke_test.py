from datetime import UTC, datetime
from unittest.mock import patch

from app.config import Settings
from services.ai.ollama_client import OllamaCloudError
from services.ai.smoke_test import SmokeTestResult, run_smoke_test
from storage.models import MarketSnapshot, NewsItem


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


def _make_news(count: int = 3) -> list[NewsItem]:
    return [
        NewsItem(
            timestamp=datetime.now(UTC),
            source=f"Source {i}",
            title=f"Title {i}",
            url=f"https://example.com/{i}",
            summary=f"Summary {i}",
            region="Chile" if i == 0 else "Global",
            topic="tasas" if i == 0 else "macro general",
            impact_score=10 - i,
        )
        for i in range(count)
    ]


def _make_snapshots() -> list[MarketSnapshot]:
    return [
        MarketSnapshot(
            timestamp=datetime.now(UTC),
            symbol="USDCLP",
            name="USD/CLP",
            price=900.0,
            change_pct=1.5,
            source="yfinance",
        )
    ]


class TestSmokeTest:
    def test_skipped_when_ai_disabled(self) -> None:
        settings = _make_settings(ai_enabled=False)
        with patch("services.ai.smoke_test.OllamaCloudClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = False
            mock_client.is_dry_run.return_value = True
            result = run_smoke_test(_make_news(), _make_snapshots())
        assert isinstance(result, SmokeTestResult)
        assert result.response is None
        assert result.metadata.validation_status == "skipped"

    def test_dry_run_returns_ok(self) -> None:
        settings = _make_settings(ai_enabled=True, ai_dry_run=True)
        with patch("services.ai.smoke_test.OllamaCloudClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = True
            mock_client.is_dry_run.return_value = True
            mock_client.settings.ai_strict_json = True
            mock_client.chat_json.return_value = (
                '{"status":"ok","summary":"x","high_impact_titles":[],"cautions":[]}'
            )
            result = run_smoke_test(_make_news(), _make_snapshots())
        assert result.ok is True
        assert result.response is not None
        assert result.response.status == "ok"

    def test_invalid_json_returns_invalid_status(self) -> None:
        settings = _make_settings(ai_enabled=True, ai_dry_run=False)
        with patch("services.ai.smoke_test.OllamaCloudClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = True
            mock_client.is_dry_run.return_value = False
            mock_client.settings.ai_strict_json = True
            mock_client.chat_json.return_value = "not json at all"
            result = run_smoke_test(_make_news(), _make_snapshots())
        assert result.response is None
        assert result.metadata.validation_status == "invalid_json"

    def test_ollama_error_returns_skipped(self) -> None:
        settings = _make_settings(ai_enabled=True, ai_dry_run=False)
        with patch("services.ai.smoke_test.OllamaCloudClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = True
            mock_client.is_dry_run.return_value = False
            mock_client.chat_json.side_effect = OllamaCloudError("boom")
            result = run_smoke_test(_make_news(), _make_snapshots())
        assert result.response is None
        assert result.metadata.validation_status == "skipped"
        assert "boom" in result.metadata.error_message

    def test_does_not_mutate_news_items(self) -> None:
        settings = _make_settings(ai_enabled=False)
        news = _make_news()
        original_scores = [n.impact_score for n in news]
        with patch("services.ai.smoke_test.OllamaCloudClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = False
            mock_client.is_dry_run.return_value = True
            run_smoke_test(news, _make_snapshots())
        assert [n.impact_score for n in news] == original_scores

    def test_respects_max_news_limit(self) -> None:
        settings = _make_settings(ai_enabled=True, ai_dry_run=True)
        news = _make_news(count=50)
        with patch("services.ai.smoke_test.OllamaCloudClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = True
            mock_client.is_dry_run.return_value = True
            mock_client.settings.ai_strict_json = True
            mock_client.chat_json.return_value = (
                '{"status":"ok","summary":"x","high_impact_titles":[],"cautions":[]}'
            )
            result = run_smoke_test(news, _make_snapshots(), max_news=10)
        assert result.metadata.input_news_count == 10
