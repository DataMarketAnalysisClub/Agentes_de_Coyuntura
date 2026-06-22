from datetime import UTC, datetime
from unittest.mock import patch

from app.config import Settings
from services.ai.editorial_pipeline import Phase3PipelineResult, run_phase3_pipeline
from storage.models import MarketSnapshot, NewsItem


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


def _make_snapshots() -> list[MarketSnapshot]:
    return [
        MarketSnapshot(
            timestamp=datetime.now(UTC),
            symbol="USDCLP",
            name="USD/CLP",
            price=900.0,
            change_pct=1.5,
            source="yfinance",
        ),
    ]


class TestPhase3Pipeline:
    def test_ai_disabled_produces_fallback_email(self) -> None:
        settings = _make_settings(ai_enabled=False)
        with (
            patch("services.ai.editorial_pipeline.run_phase2_pipeline") as mock_phase2,
            patch("services.ai.editorial_writer.OllamaCloudClient") as mock_client_class,
        ):
            from services.ai.schemas import AiIntermediateRegionalReport, AiPhase2Report
            mock_phase2.return_value = type(
                "MockResult",
                (),
                {
                    "report": AiPhase2Report(
                        status="ok",
                        generated_at=datetime.now(UTC),
                        regional_reports=[AiIntermediateRegionalReport(
                            region="Chile", executive_summary=["Hecho"]
                        )],
                    ),
                    "all_metadata": [],
                    "ok": True,
                },
            )()
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = False
            mock_client.is_dry_run.return_value = True
            result = run_phase3_pipeline(_make_news(), _make_snapshots(), max_news=5)
        assert isinstance(result, Phase3PipelineResult)
        assert result.editorial is not None
        assert result.fallback_used is True
        assert result.html != ""
        assert result.markdown != ""

    def test_pipeline_produces_html_with_charts(self) -> None:
        settings = _make_settings(ai_enabled=False)
        with (
            patch("services.ai.editorial_pipeline.run_phase2_pipeline") as mock_phase2,
            patch("services.ai.editorial_writer.OllamaCloudClient") as mock_client_class,
        ):
            from services.ai.schemas import AiIntermediateRegionalReport, AiPhase2Report
            mock_phase2.return_value = type(
                "MockResult",
                (),
                {
                    "report": AiPhase2Report(
                        status="ok",
                        generated_at=datetime.now(UTC),
                        regional_reports=[AiIntermediateRegionalReport(
                            region="Chile", executive_summary=["Hecho"]
                        )],
                    ),
                    "all_metadata": [],
                    "ok": True,
                },
            )()
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = False
            result = run_phase3_pipeline(_make_news(), _make_snapshots(), max_news=5)
        assert "plotly" in result.html.lower() or "chart" in result.html.lower()
        assert len(result.chart_fragments) > 0

    def test_pipeline_does_not_call_email_sender(self) -> None:
        settings = _make_settings(ai_enabled=False)
        with (
            patch("services.ai.editorial_pipeline.run_phase2_pipeline") as mock_phase2,
            patch("services.ai.editorial_writer.OllamaCloudClient") as mock_client_class,
            patch("services.email_sender.EmailSender") as mock_email,
        ):
            from services.ai.schemas import AiPhase2Report
            mock_phase2.return_value = type(
                "MockResult",
                (),
                {
                    "report": AiPhase2Report(
                        status="ok",
                        generated_at=datetime.now(UTC),
                    ),
                    "all_metadata": [],
                    "ok": True,
                },
            )()
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = False
            run_phase3_pipeline(_make_news(), max_news=3)
            mock_email.assert_not_called()

    def test_pipeline_does_not_mutate_news(self) -> None:
        settings = _make_settings(ai_enabled=False)
        news = _make_news()
        original = [n.title for n in news]
        with (
            patch("services.ai.editorial_pipeline.run_phase2_pipeline") as mock_phase2,
            patch("services.ai.editorial_writer.OllamaCloudClient") as mock_client_class,
        ):
            from services.ai.schemas import AiPhase2Report
            mock_phase2.return_value = type(
                "MockResult",
                (),
                {
                    "report": AiPhase2Report(
                        status="ok",
                        generated_at=datetime.now(UTC),
                    ),
                    "all_metadata": [],
                    "ok": True,
                },
            )()
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = False
            run_phase3_pipeline(news, max_news=3)
        assert [n.title for n in news] == original

    def test_pipeline_metadata_includes_editorial_stage(self) -> None:
        settings = _make_settings(ai_enabled=False)
        with (
            patch("services.ai.editorial_pipeline.run_phase2_pipeline") as mock_phase2,
            patch("services.ai.editorial_writer.OllamaCloudClient") as mock_client_class,
        ):
            from services.ai.schemas import AiPhase2Report
            mock_phase2.return_value = type(
                "MockResult",
                (),
                {
                    "report": AiPhase2Report(
                        status="ok",
                        generated_at=datetime.now(UTC),
                    ),
                    "all_metadata": [],
                    "ok": True,
                },
            )()
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = False
            result = run_phase3_pipeline(_make_news(), max_news=3)
        from services.ai.schemas import AiEditorialRunMetadata
        editorial_meta = [m for m in result.metadata if isinstance(m, AiEditorialRunMetadata)]
        assert len(editorial_meta) == 1
        assert editorial_meta[0].stage == "editorial_writer"

    def test_pipeline_charts_disabled(self) -> None:
        settings = _make_settings(ai_enabled=False)
        with (
            patch("services.ai.editorial_pipeline.run_phase2_pipeline") as mock_phase2,
            patch("services.ai.editorial_writer.OllamaCloudClient") as mock_client_class,
        ):
            from services.ai.schemas import AiPhase2Report
            mock_phase2.return_value = type(
                "MockResult",
                (),
                {
                    "report": AiPhase2Report(
                        status="ok",
                        generated_at=datetime.now(UTC),
                    ),
                    "all_metadata": [],
                    "ok": True,
                },
            )()
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = False
            result = run_phase3_pipeline(_make_news(), _make_snapshots(), max_news=3, render_charts_enabled=False)
        assert result.chart_fragments == {}
