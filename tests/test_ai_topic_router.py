from datetime import UTC, datetime
from unittest.mock import patch

from app.config import Settings
from services.ai.schemas import AiRoutedNewsInput
from services.ai.topic_router import TopicRouterResult, run_topic_router


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


def _make_routed(count: int = 3) -> list[AiRoutedNewsInput]:
    return [
        AiRoutedNewsInput(
            id=f"https://example.com/{i}",
            timestamp=datetime.now(UTC),
            source="s",
            title=f"t{i}",
            url=f"https://example.com/{i}",
            region="Chile",
            country="Chile",
            topic="tasas" if i % 2 == 0 else "commodities",
            impact_score=10 - i,
        )
        for i in range(count)
    ]


class TestTopicRouter:
    def test_skipped_when_ai_disabled(self) -> None:
        settings = _make_settings(ai_enabled=False)
        with patch("services.ai.topic_router.OllamaCloudClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = False
            mock_client.is_dry_run.return_value = True
            result = run_topic_router(_make_routed(), None, "Chile")
        assert isinstance(result, TopicRouterResult)
        assert result.response is None
        assert result.metadata.validation_status == "skipped"

    def test_dry_run_returns_valid(self) -> None:
        settings = _make_settings(ai_enabled=True, ai_dry_run=True)
        valid_json = (
            '{"status":"ok","clusters":['
            '{"region":"Chile","country":"Chile","topic":"tasas","relevance":"high",'
            '"news_urls":["https://example.com/0"],'
            '"observed_facts":["Hecho"],"interpretation":["Lectura"],'
            '"affected_assets":["USDCLP"],"watch_items":[],"cautions":[]}'
            '],"cautions":[]}'
        )
        with patch("services.ai.topic_router.OllamaCloudClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = True
            mock_client.is_dry_run.return_value = True
            mock_client.settings.ai_strict_json = True
            mock_client.chat_json.return_value = valid_json
            result = run_topic_router(_make_routed(), None, "Chile")
        assert result.ok is True
        assert result.response is not None
        assert len(result.response.clusters) == 1
        assert result.response.clusters[0].affected_assets == ["USDCLP"]

    def test_invalid_json_returns_invalid_status(self) -> None:
        settings = _make_settings(ai_enabled=True, ai_dry_run=False)
        with patch("services.ai.topic_router.OllamaCloudClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = True
            mock_client.is_dry_run.return_value = False
            mock_client.settings.ai_strict_json = True
            mock_client.chat_json.return_value = "not json"
            result = run_topic_router(_make_routed(), None, "Chile")
        assert result.response is None
        assert result.metadata.validation_status == "invalid_json"

    def test_respects_max_per_group(self) -> None:
        settings = _make_settings(ai_enabled=True, ai_dry_run=True)
        valid_json = '{"status":"ok","clusters":[],"cautions":[]}'
        routed = _make_routed(20)
        with patch("services.ai.topic_router.OllamaCloudClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = True
            mock_client.is_dry_run.return_value = True
            mock_client.settings.ai_strict_json = True
            mock_client.chat_json.return_value = valid_json
            result = run_topic_router(routed, None, "Chile", max_per_group=5)
        assert result.metadata.input_news_count <= 10
