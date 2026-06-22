from datetime import UTC, datetime
from unittest.mock import patch

from app.config import Settings
from services.ai.macro_router import MacroRouterResult, news_for_group, run_macro_router
from storage.models import NewsItem


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
            title=f"{'Chile ' if i == 0 else 'Fed '}title {i}",
            url=f"https://example.com/{i}",
            summary=f"Summary {i}",
            region="Chile" if i == 0 else "EE.UU.",
            topic="tasas",
            impact_score=10 - i,
        )
        for i in range(count)
    ]


class TestMacroRouter:
    def test_skipped_when_ai_disabled(self) -> None:
        settings = _make_settings(ai_enabled=False)
        with patch("services.ai.macro_router.OllamaCloudClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = False
            mock_client.is_dry_run.return_value = True
            result = run_macro_router(_make_news())
        assert isinstance(result, MacroRouterResult)
        assert result.response is None
        assert result.metadata.validation_status == "skipped"
        assert len(result.routed_news) > 0

    def test_dry_run_returns_valid(self) -> None:
        settings = _make_settings(ai_enabled=True, ai_dry_run=True)
        valid_json = (
            '{"status":"ok","groups":['
            '{"region":"Chile","country":"Chile","relevance":"high",'
            '"main_topics":["tasas"],"news_urls":["https://example.com/0"],'
            '"key_facts":["Hecho"],"why_it_matters":"x","cautions":[]}'
            '],"discarded_urls":[],"cautions":[]}'
        )
        with patch("services.ai.macro_router.OllamaCloudClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = True
            mock_client.is_dry_run.return_value = True
            mock_client.settings.ai_strict_json = True
            mock_client.chat_json.return_value = valid_json
            result = run_macro_router(_make_news())
        assert result.ok is True
        assert result.response is not None
        assert len(result.response.groups) == 1

    def test_invalid_json_returns_invalid_status(self) -> None:
        settings = _make_settings(ai_enabled=True, ai_dry_run=False)
        with patch("services.ai.macro_router.OllamaCloudClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = True
            mock_client.is_dry_run.return_value = False
            mock_client.settings.ai_strict_json = True
            mock_client.chat_json.return_value = "not json"
            result = run_macro_router(_make_news())
        assert result.response is None
        assert result.metadata.validation_status == "invalid_json"

    def test_ollama_error_returns_skipped(self) -> None:
        settings = _make_settings(ai_enabled=True, ai_dry_run=False)
        from services.ai.ollama_client import OllamaCloudError

        with patch("services.ai.macro_router.OllamaCloudClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = True
            mock_client.is_dry_run.return_value = False
            mock_client.chat_json.side_effect = OllamaCloudError("boom")
            result = run_macro_router(_make_news())
        assert result.response is None
        assert result.metadata.validation_status == "skipped"

    def test_news_for_group_filters_by_url(self) -> None:
        from services.ai.schemas import AiRoutedNewsInput

        routed = [
            AiRoutedNewsInput(
                id=f"https://example.com/{i}",
                timestamp=datetime.now(UTC),
                source="s",
                title=f"t{i}",
                url=f"https://example.com/{i}",
                region="Chile",
                impact_score=5,
            )
            for i in range(5)
        ]
        filtered = news_for_group(routed, ["https://example.com/1", "https://example.com/3"])
        assert len(filtered) == 2
        assert {item.url for item in filtered} == {"https://example.com/1", "https://example.com/3"}

    def test_does_not_mutate_news(self) -> None:
        settings = _make_settings(ai_enabled=False)
        news = _make_news()
        original = [n.title for n in news]
        with patch("services.ai.macro_router.OllamaCloudClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = False
            mock_client.is_dry_run.return_value = True
            run_macro_router(news)
        assert [n.title for n in news] == original
