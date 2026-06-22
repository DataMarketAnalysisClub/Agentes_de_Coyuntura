"""Tests that RSS/scraping news are not lost in the deterministic fallback.

When IA is disabled or dry-run produces empty groups, the phase 2 pipeline
must still produce regional_reports with the actual headlines from
RSS + scraping, not an empty report.
"""

from datetime import UTC, datetime
from unittest.mock import patch

from app.config import Settings
from services.ai.editorial_pipeline import run_phase3_pipeline
from services.ai.editorial_writer import build_deterministic_editorial
from services.ai.pipeline import run_phase2_pipeline
from storage.models import NewsItem


def _make_settings(
    ai_enabled: bool = False,
    ai_dry_run: bool = True,
) -> Settings:
    return Settings(
        ai_enabled=ai_enabled,
        ai_dry_run=ai_dry_run,
        ollama_api_key="test-key",
        ollama_model="gpt-oss:120b",
        ollama_base_url="https://ollama.com",
        ollama_timeout_seconds=5.0,
        ollama_temperature=0.2,
        ollama_max_retries=1,
    )


def _make_rss_scraping_news() -> list[NewsItem]:
    """Simulate realistic RSS + scraping news from the actual sources."""
    return [
        NewsItem(
            timestamp=datetime.now(UTC),
            source="Federal Reserve",
            title="Fed cuts rates by 25bps amid cooling inflation",
            url="https://example.com/fed-1",
            summary="The Federal Reserve cut its benchmark rate.",
            region="EE.UU.",
            topic="bancos centrales",
            impact_score=9,
        ),
        NewsItem(
            timestamp=datetime.now(UTC),
            source="Ministerio de Hacienda",
            title="Hacienda fija trayectoria fiscal para 2026",
            url="https://example.com/hacienda-1",
            summary="Politica fiscal anunciada.",
            region="Chile",
            topic="politica fiscal",
            impact_score=8,
        ),
        NewsItem(
            timestamp=datetime.now(UTC),
            source="ECB",
            title="ECB holds rates steady, signals patience",
            url="https://example.com/ecb-1",
            summary="ECB decision.",
            region="Eurozona",
            topic="bancos centrales",
            impact_score=7,
        ),
        NewsItem(
            timestamp=datetime.now(UTC),
            source="MarketWatch",
            title="Copper prices surge 3% on China demand hopes",
            url="https://example.com/copper-1",
            summary="Copper rally on China data.",
            region="Global",
            topic="commodities",
            impact_score=6,
        ),
        NewsItem(
            timestamp=datetime.now(UTC),
            source="La Tercera Pulso",
            title="Banco Central de Chile mantiene TPM en 5.5%",
            url="https://example.com/bcch-1",
            summary="BCCh mantiene tasa.",
            region="Chile",
            topic="bancos centrales",
            impact_score=7,
        ),
        NewsItem(
            timestamp=datetime.now(UTC),
            source="Investing.com",
            title="USD/CLP rises above 900 on dollar strength",
            url="https://example.com/usdclp-1",
            summary="Dolar sube.",
            region="Chile",
            topic="forex",
            impact_score=6,
        ),
    ]


class TestNoNewsLossInFallback:
    def test_phase2_fallback_has_regional_reports(self) -> None:
        """When IA is disabled, phase 2 must still produce regional_reports."""
        settings = _make_settings(ai_enabled=False)
        news = _make_rss_scraping_news()
        with patch("services.ai.pipeline.OllamaCloudClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = False
            mock_client.is_dry_run.return_value = True
            result = run_phase2_pipeline(news, max_news=10)
        assert result.report is not None
        assert len(result.report.regional_reports) > 0

    def test_phase2_fallback_regional_reports_have_titles(self) -> None:
        """Regional reports in fallback must contain actual headlines."""
        settings = _make_settings(ai_enabled=False)
        news = _make_rss_scraping_news()
        with patch("services.ai.pipeline.OllamaCloudClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = False
            mock_client.is_dry_run.return_value = True
            result = run_phase2_pipeline(news, max_news=10)
        assert result.report is not None
        all_facts: list[str] = []
        for regional in result.report.regional_reports:
            all_facts.extend(regional.executive_summary)
            for cluster in regional.topic_clusters:
                all_facts.extend(cluster.observed_facts)
        # At least some original titles should appear
        assert any("Fed" in f or "Hacienda" in f or "ECB" in f for f in all_facts)

    def test_phase2_fallback_includes_chile_section(self) -> None:
        """Chile news should produce a Chile regional report in fallback."""
        settings = _make_settings(ai_enabled=False)
        news = _make_rss_scraping_news()
        with patch("services.ai.pipeline.OllamaCloudClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = False
            mock_client.is_dry_run.return_value = True
            result = run_phase2_pipeline(news, max_news=10)
        assert result.report is not None
        labels = [r.country or r.region for r in result.report.regional_reports]
        assert "Chile" in labels

    def test_phase2_fallback_topic_clusters_have_urls(self) -> None:
        """Topic clusters in fallback must have real news_urls."""
        settings = _make_settings(ai_enabled=False)
        news = _make_rss_scraping_news()
        with patch("services.ai.pipeline.OllamaCloudClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = False
            mock_client.is_dry_run.return_value = True
            result = run_phase2_pipeline(news, max_news=10)
        assert result.report is not None
        all_urls: list[str] = []
        for regional in result.report.regional_reports:
            for cluster in regional.topic_clusters:
                all_urls.extend(cluster.news_urls)
        assert len(all_urls) > 0
        assert all(u.startswith("https://") for u in all_urls)

    def test_phase3_fallback_email_has_regional_sections(self) -> None:
        """Phase 3 fallback email must have sections beyond Visualizaciones."""
        settings = _make_settings(ai_enabled=False)
        news = _make_rss_scraping_news()
        with (
            patch("services.ai.editorial_pipeline.run_phase2_pipeline") as mock_phase2,
            patch("services.ai.editorial_writer.OllamaCloudClient") as mock_client_class,
        ):
            from services.ai.pipeline import run_phase2_pipeline as real_phase2

            with patch("services.ai.pipeline.OllamaCloudClient") as mock_p2_client:
                mock_p2 = mock_p2_client.return_value
                mock_p2.settings = settings
                mock_p2.is_enabled.return_value = False
                mock_p2.is_dry_run.return_value = True
                real_result = real_phase2(news, max_news=10)

            mock_phase2.return_value = real_result
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = False
            result = run_phase3_pipeline(news, max_news=10, render_charts_enabled=False)
        assert result.editorial is not None
        non_viz_sections = [s for s in result.editorial.sections if s.heading != "Visualizaciones"]
        assert len(non_viz_sections) > 0

    def test_phase3_fallback_email_contains_headlines(self) -> None:
        """The fallback email must contain actual headlines in bullets/body."""
        settings = _make_settings(ai_enabled=False)
        news = _make_rss_scraping_news()
        with (
            patch("services.ai.editorial_pipeline.run_phase2_pipeline") as mock_phase2,
            patch("services.ai.editorial_writer.OllamaCloudClient") as mock_client_class,
        ):
            from services.ai.pipeline import run_phase2_pipeline as real_phase2

            with patch("services.ai.pipeline.OllamaCloudClient") as mock_p2_client:
                mock_p2 = mock_p2_client.return_value
                mock_p2.settings = settings
                mock_p2.is_enabled.return_value = False
                mock_p2.is_dry_run.return_value = True
                real_result = real_phase2(news, max_news=10)

            mock_phase2.return_value = real_result
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = False
            result = run_phase3_pipeline(news, max_news=10, render_charts_enabled=False)
        assert result.editorial is not None
        all_parts: list[str] = []
        for s in result.editorial.sections:
            all_parts.extend(s.body)
            all_parts.extend(s.bullets)
        all_text = " ".join(all_parts)
        assert any(title in all_text for title in ["Fed", "Hacienda", "ECB", "Copper", "TPM"])

    def test_deterministic_editorial_with_empty_report_still_works(self) -> None:
        """If phase2 report has no regional_reports, editorial should still build."""
        from services.ai.schemas import AiPhase2Report

        report = AiPhase2Report(
            status="ok",
            generated_at=datetime.now(UTC),
            regional_reports=[],
            global_summary=["Resumen global de fallback."],
            editorial_cautions=["Cautela."],
        )
        email = build_deterministic_editorial(report, available_ids=[])
        assert email.status == "ok"
        assert len(email.sections) >= 1

    def test_phase2_fallback_preserves_sources(self) -> None:
        """The fallback should preserve source diversity from RSS + scraping."""
        settings = _make_settings(ai_enabled=False)
        news = _make_rss_scraping_news()
        with patch("services.ai.pipeline.OllamaCloudClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = False
            mock_client.is_dry_run.return_value = True
            result = run_phase2_pipeline(news, max_news=10)
        assert result.report is not None
        # At least 2 different regions should be represented
        regions = {r.region for r in result.report.regional_reports}
        assert len(regions) >= 2
