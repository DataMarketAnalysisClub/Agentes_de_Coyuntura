from datetime import UTC, datetime
from unittest.mock import patch

from app.config import Settings
from services.ai.pipeline import Phase2PipelineResult, run_phase2_pipeline
from storage.models import NewsItem


def _make_settings(
    ai_enabled: bool = False,
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


def _make_news(count: int = 5) -> list[NewsItem]:
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


class TestPhase2Pipeline:
    def test_ai_disabled_produces_fallback_report(self) -> None:
        settings = _make_settings(ai_enabled=False)
        with (
            patch("services.ai.macro_router.OllamaCloudClient") as mock_macro,
            patch("services.ai.topic_router.OllamaCloudClient") as mock_topic,
            patch("services.ai.pipeline.OllamaCloudClient") as mock_pipe,
        ):
            for mock_client in (mock_macro.return_value, mock_topic.return_value, mock_pipe.return_value):
                mock_client.settings = settings
                mock_client.is_enabled.return_value = False
                mock_client.is_dry_run.return_value = True
            result = run_phase2_pipeline(_make_news(), max_news=5)
        assert isinstance(result, Phase2PipelineResult)
        # When AI is disabled, macro router returns skipped, pipeline builds fallback
        assert result.report is not None or result.metadata_list[0].validation_status == "skipped"

    def test_pipeline_does_not_call_email_sender(self) -> None:
        settings = _make_settings(ai_enabled=False)
        with (
            patch("services.ai.macro_router.OllamaCloudClient") as mock_macro,
            patch("services.ai.topic_router.OllamaCloudClient") as mock_topic,
            patch("services.ai.pipeline.OllamaCloudClient") as mock_pipe,
            patch("services.email_sender.EmailSender") as mock_email,
        ):
            for mock_client in (mock_macro.return_value, mock_topic.return_value, mock_pipe.return_value):
                mock_client.settings = settings
                mock_client.is_enabled.return_value = False
                mock_client.is_dry_run.return_value = True
            run_phase2_pipeline(_make_news(), max_news=3)
            mock_email.assert_not_called()

    def test_pipeline_does_not_mutate_news(self) -> None:
        settings = _make_settings(ai_enabled=False)
        news = _make_news()
        original = [n.title for n in news]
        with (
            patch("services.ai.macro_router.OllamaCloudClient") as mock_macro,
            patch("services.ai.topic_router.OllamaCloudClient") as mock_topic,
            patch("services.ai.pipeline.OllamaCloudClient") as mock_pipe,
        ):
            for mock_client in (mock_macro.return_value, mock_topic.return_value, mock_pipe.return_value):
                mock_client.settings = settings
                mock_client.is_enabled.return_value = False
                mock_client.is_dry_run.return_value = True
            run_phase2_pipeline(news, max_news=3)
        assert [n.title for n in news] == original

    def test_pipeline_metadata_tracks_stages(self) -> None:
        settings = _make_settings(ai_enabled=False)
        with (
            patch("services.ai.macro_router.OllamaCloudClient") as mock_macro,
            patch("services.ai.topic_router.OllamaCloudClient") as mock_topic,
            patch("services.ai.pipeline.OllamaCloudClient") as mock_pipe,
        ):
            for mock_client in (mock_macro.return_value, mock_topic.return_value, mock_pipe.return_value):
                mock_client.settings = settings
                mock_client.is_enabled.return_value = False
                mock_client.is_dry_run.return_value = True
            result = run_phase2_pipeline(_make_news(), max_news=3)
        assert len(result.metadata_list) >= 1
        assert result.metadata_list[0].stage == "macro_router"

    def test_pipeline_respects_max_news(self) -> None:
        settings = _make_settings(ai_enabled=False)
        news = _make_news(50)
        with (
            patch("services.ai.macro_router.OllamaCloudClient") as mock_macro,
            patch("services.ai.topic_router.OllamaCloudClient") as mock_topic,
            patch("services.ai.pipeline.OllamaCloudClient") as mock_pipe,
        ):
            for mock_client in (mock_macro.return_value, mock_topic.return_value, mock_pipe.return_value):
                mock_client.settings = settings
                mock_client.is_enabled.return_value = False
                mock_client.is_dry_run.return_value = True
            result = run_phase2_pipeline(news, max_news=10)
        assert result.metadata_list[0].input_news_count == 10
