from datetime import UTC, datetime

from services.ai.editorial_email_formatter import (
    render_editorial_email_html,
    render_editorial_email_markdown,
)
from services.ai.schemas import (
    AiChartSpec,
    AiEditorialEmail,
    AiEditorialSection,
)


def _make_email() -> AiEditorialEmail:
    section = AiEditorialSection(
        heading="Chile",
        body=["Hacienda anuncia politica fiscal."],
        bullets=["Hecho 1", "Hecho 2"],
        chart_ids=["change_pct_bar"],
        cautions=["Cautela 1"],
    )
    chart = AiChartSpec(
        chart_id="change_pct_bar",
        chart_type="bar_change_pct",
        title="Variacion %",
    )
    return AiEditorialEmail(
        status="ok",
        generated_at=datetime.now(UTC),
        subject="DMAC Coyuntura - 20 jun 2026",
        preheader="Resumen ejecutivo breve",
        headline="Coyuntura regional",
        executive_summary=["Punto 1", "Punto 2"],
        market_context=["Contexto 1"],
        sections=[section],
        risk_flags=["Flag 1"],
        chart_specs=[chart],
        source_notes=["Federal Reserve", "ECB"],
        editorial_cautions=["Cautela general"],
    )


class TestEditorialEmailFormatter:
    def test_html_includes_subject_and_headline(self) -> None:
        html = render_editorial_email_html(_make_email())
        assert "DMAC Coyuntura" in html
        assert "Coyuntura regional" in html

    def test_html_includes_preheader(self) -> None:
        html = render_editorial_email_html(_make_email())
        assert "Resumen ejecutivo breve" in html

    def test_html_includes_sections(self) -> None:
        html = render_editorial_email_html(_make_email())
        assert "Chile" in html
        assert "Hacienda anuncia" in html
        assert "Hecho 1" in html

    def test_html_includes_cautions(self) -> None:
        html = render_editorial_email_html(_make_email())
        assert "Cautela general" in html
        assert "recomendacion de inversion" in html

    def test_html_includes_chart_fragment(self) -> None:
        email = _make_email()
        fragments = {"change_pct_bar": "<div>FAKE_CHART</div>"}
        html = render_editorial_email_html(email, fragments)
        assert "FAKE_CHART" in html

    def test_html_skips_missing_chart(self) -> None:
        email = _make_email()
        html = render_editorial_email_html(email, {})
        assert "FAKE_CHART" not in html

    def test_html_escapes_content(self) -> None:
        email = _make_email()
        email.sections[0].body = ["<script>alert('x')</script>"]
        html = render_editorial_email_html(email)
        assert "<script>" not in html
        assert "&lt;script&gt;" in html

    def test_markdown_includes_headline_and_sections(self) -> None:
        md = render_editorial_email_markdown(_make_email())
        assert "# Coyuntura regional" in md
        assert "## Chile" in md
        assert "Hacienda anuncia" in md
        assert "**Asunto:**" in md

    def test_markdown_includes_cautions(self) -> None:
        md = render_editorial_email_markdown(_make_email())
        assert "Cautelas editoriales" in md
        assert "recomendacion de inversion" in md

    def test_markdown_lists_chart_ids(self) -> None:
        md = render_editorial_email_markdown(_make_email())
        assert "change_pct_bar" in md

    def test_html_minimal_email(self) -> None:
        email = AiEditorialEmail(
            status="ok",
            generated_at=datetime.now(UTC),
            subject="Test",
        )
        html = render_editorial_email_html(email)
        assert "<html" in html
        assert "Test" in html
