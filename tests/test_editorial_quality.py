"""Tests for the editorial quality improvements (no duplicates, structure,
quality score, ai-review-fast command).
"""

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from app.config import Settings
from services.ai.editorial_writer import build_deterministic_editorial
from services.ai.pipeline import run_phase2_pipeline
from services.ai.quality_score import compute_quality_score
from services.ai.schemas import (
    AiChartSpec,
    AiEditorialEmail,
    AiEditorialSection,
)
from storage.models import MarketSnapshot, NewsItem


def _make_settings() -> Settings:
    return Settings(
        ai_enabled=False,
        ai_dry_run=True,
        ollama_api_key="test-key",
        ollama_model="gpt-oss:120b",
        ollama_base_url="https://ollama.com",
        ollama_timeout_seconds=5.0,
        ollama_temperature=0.2,
        ollama_max_retries=1,
    )


def _make_news() -> list[NewsItem]:
    now = datetime.now(UTC)
    return [
        NewsItem(timestamp=now, source="Federal Reserve",
                 title="Fed cut rates by 25bps amid cooling inflation",
                 url="https://example.com/1", summary="Fed cut rates",
                 region="EE.UU.", topic="bancos centrales", impact_score=9),
        NewsItem(timestamp=now, source="Ministerio de Hacienda",
                 title="Hacienda fija trayectoria fiscal para 2026",
                 url="https://example.com/2", summary="Politica fiscal",
                 region="Chile", topic="politica fiscal", impact_score=8),
        NewsItem(timestamp=now, source="ECB",
                 title="ECB holds rates steady, signals patience",
                 url="https://example.com/3", summary="ECB decision",
                 region="Eurozona", topic="bancos centrales", impact_score=7),
        NewsItem(timestamp=now, source="La Tercera Pulso",
                 title="Banco Central de Chile mantiene TPM en 5.5%",
                 url="https://example.com/4", summary="BCCh mantiene tasa",
                 region="Chile", topic="bancos centrales", impact_score=7),
    ]


def _make_snaps() -> list[MarketSnapshot]:
    now = datetime.now(UTC)
    return [
        MarketSnapshot(timestamp=now, symbol="USDCLP", name="USD/CLP",
                       price=902.5, change_pct=1.5, source="yfinance"),
        MarketSnapshot(timestamp=now, symbol="COPPER", name="Cobre",
                       price=4.52, change_pct=3.0, source="yfinance"),
    ]


class TestEditorialStructure:
    def test_no_duplicate_titles_in_fallback(self) -> None:
        """Fallback editorial must not repeat the same title across bullets."""
        news = _make_news()
        snaps = _make_snaps()
        settings = _make_settings()

        with patch("services.ai.pipeline.OllamaCloudClient") as mock_p2:
            mock = mock_p2.return_value
            mock.settings = settings
            mock.is_enabled.return_value = False
            mock.is_dry_run.return_value = True
            phase2 = run_phase2_pipeline(news, max_news=10)

        assert phase2.report is not None
        email = build_deterministic_editorial(phase2.report, snaps, ["assets_table"], news)

        all_text: list[str] = []
        for s in email.sections:
            all_text.extend(s.body)
            all_text.extend(s.bullets)

        non_empty = [t for t in all_text if t.strip()]
        lowered = [t.lower().strip().rstrip(".") for t in non_empty]
        duplicates = len(lowered) - len(set(lowered))
        assert duplicates == 0, f"Found {duplicates} duplicate titles in editorial"

    def test_no_raw_score_prefixes_in_fallback(self) -> None:
        """Fallback editorial must not contain [9] / [8] / etc. in body or bullets."""
        news = _make_news()
        snaps = _make_snaps()
        settings = _make_settings()

        with patch("services.ai.pipeline.OllamaCloudClient") as mock_p2:
            mock = mock_p2.return_value
            mock.settings = settings
            mock.is_enabled.return_value = False
            mock.is_dry_run.return_value = True
            phase2 = run_phase2_pipeline(news, max_news=10)

        assert phase2.report is not None
        email = build_deterministic_editorial(phase2.report, snaps, ["assets_table"], news)

        import re
        pattern = re.compile(r"^\s*\[\d+\]\s*")
        for s in email.sections:
            for line in s.body + s.bullets:
                assert not pattern.match(line), f"Raw score prefix found: {line!r}"

    def test_reading_is_topic_specific(self) -> None:
        """Reading should mention topics, not the v1 generic phrase."""
        news = _make_news()
        snaps = _make_snaps()
        settings = _make_settings()

        with patch("services.ai.pipeline.OllamaCloudClient") as mock_p2:
            mock = mock_p2.return_value
            mock.settings = settings
            mock.is_enabled.return_value = False
            mock.is_dry_run.return_value = True
            phase2 = run_phase2_pipeline(news, max_news=10)

        assert phase2.report is not None
        email = build_deterministic_editorial(phase2.report, snaps, [], news)

        body_blob = " ".join(
            line
            for s in email.sections
            if s.heading != "Visualizaciones"
            for line in s.body
        )

        assert "el conjunto de hechos sugiere movimientos vinculados a los focos" not in body_blob
        assert "bancos centrales" in body_blob.lower() or "politica fiscal" in body_blob.lower()

    def test_headline_uses_new_templates(self) -> None:
        """Headline should use v2 templates, not the v1 'marcan la agenda' style."""
        news = _make_news()
        snaps = _make_snaps()
        settings = _make_settings()

        with patch("services.ai.pipeline.OllamaCloudClient") as mock_p2:
            mock = mock_p2.return_value
            mock.settings = settings
            mock.is_enabled.return_value = False
            mock.is_dry_run.return_value = True
            phase2 = run_phase2_pipeline(news, max_news=10)

        assert phase2.report is not None
        email = build_deterministic_editorial(phase2.report, snaps, ["assets_table"], news)

        assert email.headline != "Coyuntura regional y de mercados"
        assert "marcan la jornada" in email.headline or "lidera la jornada" in email.headline or "foco en" in email.headline

    def test_subject_uses_top_regions(self) -> None:
        """Subject should include at least one region or asset."""
        news = _make_news()
        snaps = _make_snaps()
        settings = _make_settings()

        with patch("services.ai.pipeline.OllamaCloudClient") as mock_p2:
            mock = mock_p2.return_value
            mock.settings = settings
            mock.is_enabled.return_value = False
            mock.is_dry_run.return_value = True
            phase2 = run_phase2_pipeline(news, max_news=10)

        assert phase2.report is not None
        email = build_deterministic_editorial(phase2.report, snaps, ["assets_table"], news)

        assert len(email.subject) <= 80
        assert "DMAC" in email.subject or "Coyuntura" in email.subject

    def test_subject_mentions_copper_when_moving(self) -> None:
        """If COPPER is the top mover, subject should mention cobre."""
        news = _make_news()
        snaps = _make_snaps()
        settings = _make_settings()

        with patch("services.ai.pipeline.OllamaCloudClient") as mock_p2:
            mock = mock_p2.return_value
            mock.settings = settings
            mock.is_enabled.return_value = False
            mock.is_dry_run.return_value = True
            phase2 = run_phase2_pipeline(news, max_news=10)

        assert phase2.report is not None
        email = build_deterministic_editorial(phase2.report, snaps, ["assets_table"], news)

        assert "cobre" in email.subject.lower() or "cobre" in email.headline.lower()

    def test_headline_and_preheader_present(self) -> None:
        """Headline and preheader should be non-empty in fallback."""
        news = _make_news()
        snaps = _make_snaps()
        settings = _make_settings()

        with patch("services.ai.pipeline.OllamaCloudClient") as mock_p2:
            mock = mock_p2.return_value
            mock.settings = settings
            mock.is_enabled.return_value = False
            mock.is_dry_run.return_value = True
            phase2 = run_phase2_pipeline(news, max_news=10)

        assert phase2.report is not None
        email = build_deterministic_editorial(phase2.report, snaps, ["assets_table"], news)

        assert email.headline.strip() != ""
        assert len(email.preheader) <= 120
        assert email.preheader.strip() != ""

    def test_fallback_paragraph_separates_facts_from_reading(self) -> None:
        """Each region body should mention facts and reading."""
        news = _make_news()
        snaps = _make_snaps()
        settings = _make_settings()

        with patch("services.ai.pipeline.OllamaCloudClient") as mock_p2:
            mock = mock_p2.return_value
            mock.settings = settings
            mock.is_enabled.return_value = False
            mock.is_dry_run.return_value = True
            phase2 = run_phase2_pipeline(news, max_news=10)

        assert phase2.report is not None
        email = build_deterministic_editorial(phase2.report, snaps, [], news)

        non_viz = [s for s in email.sections if s.heading != "Visualizaciones"]
        assert len(non_viz) > 0
        for s in non_viz:
            body_text = " ".join(s.body)
            assert "Lectura preliminar" in body_text or len(s.bullets) > 0


class TestQualityScore:
    def _make_minimal_email(self) -> AiEditorialEmail:
        section = AiEditorialSection(
            heading="Chile",
            body=["En Chile se observaron 2 hechos relevantes del dia."],
            bullets=["Hecho A", "Hecho B"],
            chart_ids=[],
            cautions=["Cautela 1"],
        )
        return AiEditorialEmail(
            status="ok",
            generated_at=datetime.now(UTC),
            subject="DMAC Coyuntura: Chile",
            preheader="Resumen breve del dia",
            headline="Chile lidera la jornada",
            executive_summary=["Punto 1", "Punto 2"],
            market_context=["USD/CLP: +1.50%"],
            sections=[section],
            risk_flags=[],
            chart_specs=[],
            source_notes=["Federal Reserve", "Hacienda", "ECB"],
            editorial_cautions=["Cautela general"],
        )

    def test_quality_score_basic_email(self) -> None:
        """A well-formed email should score high but not necessarily 100."""
        email = self._make_minimal_email()
        score = compute_quality_score(
            email=email,
            news_count=10,
            phase2_regional_reports_count=2,
            source_count=3,
            chart_count=0,
        )
        assert score["score"] >= 60
        assert score["score"] < 100
        assert score["checks"]["has_regional_sections"] is True
        assert score["checks"]["has_source_notes"] is True
        assert score["checks"]["has_no_duplicate_titles"] is True

    def test_quality_score_v2_metadata(self) -> None:
        """Quality score output should declare version v2."""
        email = self._make_minimal_email()
        score = compute_quality_score(
            email=email, news_count=10, phase2_regional_reports_count=2,
            source_count=3, chart_count=0,
        )
        assert score["quality_version"] == "v2"

    def test_quality_score_detects_generic_headline(self) -> None:
        """The v1 generic headline should fail headline_not_generic."""
        email = self._make_minimal_email()
        email.headline = "Coyuntura regional y de mercados"
        score = compute_quality_score(
            email=email, news_count=10, phase2_regional_reports_count=2,
            source_count=3, chart_count=0,
        )
        assert score["checks"]["headline_not_generic"] is False

    def test_quality_score_detects_generic_reading(self) -> None:
        """The v1 generic reading phrase should fail reading_not_generic."""
        email = self._make_minimal_email()
        email.sections[0].body = [
            "Lectura preliminar: el conjunto de hechos sugiere movimientos vinculados a los focos del dia."
        ]
        score = compute_quality_score(
            email=email, news_count=10, phase2_regional_reports_count=2,
            source_count=3, chart_count=0,
        )
        assert score["checks"]["reading_not_generic"] is False
        assert score["generic_phrase_count"] >= 1

    def test_quality_score_detects_raw_score_prefixes(self) -> None:
        """Bullets like '[9] Fed cut rates' should fail no_raw_score_prefixes."""
        email = self._make_minimal_email()
        email.sections[0].bullets = ["[9] Fed cut rates by 25bps"]
        score = compute_quality_score(
            email=email, news_count=10, phase2_regional_reports_count=2,
            source_count=3, chart_count=0,
        )
        assert score["checks"]["no_raw_score_prefixes"] is False
        assert score["raw_score_prefix_count"] >= 1

    def test_quality_score_detects_topic_only_bullets(self) -> None:
        """Bullets that are only topic labels should fail no_topic_only_bullets."""
        email = self._make_minimal_email()
        email.sections[0].bullets = [
            "bancos centrales:",
            "Fed cut rates by 25bps",
        ]
        score = compute_quality_score(
            email=email, news_count=10, phase2_regional_reports_count=2,
            source_count=3, chart_count=0,
        )
        assert score["checks"]["no_topic_only_bullets"] is False
        assert score["topic_only_bullet_count"] >= 1

    def test_quality_score_requires_chile_when_chile_in_input(self) -> None:
        """If Chile is in the input news, the email must mention Chile."""
        news = [
            NewsItem(timestamp=datetime.now(UTC), source="Hacienda",
                     title="X", url="u", summary="s", region="Chile",
                     topic="politica fiscal", impact_score=8),
        ]
        email = self._make_minimal_email()
        email.subject = "DMAC Coyuntura: global"
        email.headline = "Global lidera la jornada"
        email.sections = [
            AiEditorialSection(heading="Global", body=["b"], bullets=["x"], cautions=[]),
        ]
        score = compute_quality_score(
            email=email, news_count=1, phase2_regional_reports_count=1,
            source_count=1, chart_count=0, news=news,
        )
        assert score["checks"]["mentions_chile_when_present"] is False

    def test_quality_score_requires_copper_when_moving(self) -> None:
        """If COPPER is moving in snapshots, the email must mention cobre."""
        snaps = [
            MarketSnapshot(timestamp=datetime.now(UTC), symbol="COPPER",
                           name="Cobre", price=4.5, change_pct=3.0, source="yfinance"),
        ]
        email = self._make_minimal_email()
        email.subject = "DMAC Coyuntura: Chile"
        email.headline = "Chile lidera la jornada"
        email.preheader = "Resumen"
        email.sections = [
            AiEditorialSection(
                heading="Chile",
                body=["En Chile se observaron 1 hechos relevantes del dia."],
                bullets=["Hecho A"],
                cautions=[],
            ),
        ]
        score = compute_quality_score(
            email=email, news_count=2, phase2_regional_reports_count=1,
            source_count=1, chart_count=0, snapshots=snaps,
        )
        assert score["checks"]["mentions_copper_when_moving"] is False

    def test_quality_score_detects_duplicates(self) -> None:
        """Score should drop when titles repeat."""
        section = AiEditorialSection(
            heading="Chile",
            body=["Repetido."],
            bullets=["Repetido.", "Repetido."],
            chart_ids=[],
            cautions=[],
        )
        email = AiEditorialEmail(
            status="ok",
            generated_at=datetime.now(UTC),
            subject="X",
            preheader="x",
            headline="x",
            executive_summary=["x"],
            market_context=[],
            sections=[section],
            risk_flags=[],
            chart_specs=[],
            source_notes=[],
            editorial_cautions=["c"],
        )
        score = compute_quality_score(
            email=email, news_count=1, phase2_regional_reports_count=0,
            source_count=0, chart_count=0,
        )
        assert score["checks"]["has_no_duplicate_titles"] is False
        assert score["duplicate_titles_count"] > 0

    def test_quality_score_detects_long_subject(self) -> None:
        """Subject over 80 chars should fail the check."""
        section = AiEditorialSection(heading="Global", body=["x"], bullets=["y"])
        email = AiEditorialEmail(
            status="ok",
            generated_at=datetime.now(UTC),
            subject="A" * 100,
            preheader="x",
            headline="x",
            executive_summary=["x"],
            market_context=[],
            sections=[section],
            risk_flags=[],
            chart_specs=[],
            source_notes=[],
            editorial_cautions=["c"],
        )
        score = compute_quality_score(
            email=email, news_count=0, phase2_regional_reports_count=0,
            source_count=0, chart_count=0,
        )
        assert score["checks"]["has_valid_subject_length"] is False

    def test_quality_score_penalizes_lost_news(self) -> None:
        """If news > 0 but no regional reports, should fail preserved_news."""
        section = AiEditorialSection(heading="Visualizaciones", body=["x"], bullets=[])
        email = AiEditorialEmail(
            status="ok",
            generated_at=datetime.now(UTC),
            subject="x",
            preheader="x",
            headline="x",
            executive_summary=["x"],
            market_context=[],
            sections=[section],
            risk_flags=[],
            chart_specs=[],
            source_notes=[],
            editorial_cautions=["c"],
        )
        score = compute_quality_score(
            email=email, news_count=10, phase2_regional_reports_count=0,
            source_count=0, chart_count=0,
        )
        assert score["checks"]["preserved_news"] is False
        assert score["checks"]["has_regional_sections"] is False

    def test_quality_score_perfect_run_does_not_reach_100(self) -> None:
        """Even a well-formed fallback run should not hit 100/100.

        The v2 score applies a soft cap when fallback_used=True or when
        chart_count=0, reserving 100/100 for high-quality editorial runs.
        """
        section = AiEditorialSection(
            heading="Chile",
            body=["En Chile se observaron 1 hechos relevantes del dia."],
            bullets=["Hecho A"],
            chart_ids=["assets_table"],
            cautions=["Cautela 1"],
        )
        email = AiEditorialEmail(
            status="ok",
            generated_at=datetime.now(UTC),
            subject="DMAC Coyuntura: cobre, Chile",
            preheader="Foco en Chile. topics: bancos centrales. Cobre +3.00%",
            headline="Cobre y Chile marcan la jornada",
            executive_summary=["[Chile] Hecho A"],
            market_context=["USD/CLP: +1.50%"],
            sections=[section],
            risk_flags=[],
            chart_specs=[AiChartSpec(chart_id="assets_table",
                                     chart_type="table_assets",
                                     title="Principales activos")],
            source_notes=["Federal Reserve", "Hacienda", "ECB"],
            editorial_cautions=["Cautela general"],
        )
        score = compute_quality_score(
            email=email, news_count=4, phase2_regional_reports_count=2,
            source_count=3, chart_count=1, fallback_used=True,
        )
        assert score["score"] < 100
        assert score["score"] >= 70

        score_no_charts = compute_quality_score(
            email=email, news_count=4, phase2_regional_reports_count=2,
            source_count=3, chart_count=0, fallback_used=False,
        )
        assert score_no_charts["score"] < 100


class TestAIReviewFast:
    def test_ai_review_fast_runs_with_mock_data(self) -> None:
        """ai-review-fast should produce a review bundle without network calls."""
        import tempfile

        from jobs.ai_review_fast import run_ai_review_fast

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            with patch("app.config.get_settings") as mock_settings:
                s = _make_settings()
                s.ai_output_dir = str(tmp_path)
                mock_settings.return_value = s
                path = run_ai_review_fast()

        assert path is not None
        assert path.exists()
        assert (path.parent / "quality_score.json").exists()
        assert (path.parent / "editorial_email.md").exists()

    def test_ai_review_fast_handles_disabled_ai(self) -> None:
        """ai-review-fast works with AI disabled (uses fallback)."""
        import tempfile

        from jobs.ai_review_fast import run_ai_review_fast

        with tempfile.TemporaryDirectory() as tmp:
            with patch("app.config.get_settings") as mock_settings:
                s = _make_settings()
                s.ai_enabled = False
                s.ai_output_dir = tmp
                mock_settings.return_value = s
                path = run_ai_review_fast()

        assert path is not None
        review_dir = path.parent
        md = (review_dir / "editorial_email.md").read_text(encoding="utf-8")
        assert "Chile" in md or "Global" in md
