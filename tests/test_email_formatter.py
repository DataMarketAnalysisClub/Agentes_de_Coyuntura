from services.email_formatter import build_email_html, text_to_html


def test_text_to_html_escapes_content() -> None:
    """text_to_html must escape HTML-significant characters and keep them readable."""
    html = text_to_html("Titulo\n<script>alert('x')</script>")

    assert "&lt;script&gt;" in html
    assert "alert(&#x27;x&#x27;)" in html
    assert "<script>" not in html


def test_build_email_html_includes_subject_and_body() -> None:
    """build_email_html must wrap the subject and the body in a styled template."""
    html = build_email_html("DMAC Test", "Contenido de prueba")

    assert "DMAC Test" in html
    assert "Contenido de prueba" in html
    assert "<!doctype html>" in html
    assert "DMAC Brief" in html


def test_build_email_html_omits_empty_snapshots_table() -> None:
    """If no snapshots have data, the email shows a friendly placeholder, not 's/d' rows."""
    from datetime import UTC, datetime

    from storage.models import MarketSnapshot

    snap = MarketSnapshot(
        timestamp=datetime.now(UTC),
        symbol="USDCLP", name="USD/CLP",
        price=None, change_pct=None, source="yfinance",
    )
    html = build_email_html("DMAC", "Resumen", snapshots=[snap])
    assert "Mercado cerrado" in html
    assert "USD/CLP" not in html or "s/d" not in html


def test_build_email_html_includes_assets_table_when_data_available() -> None:
    """Snapshots with prices must render a clean table inside the email body."""
    from datetime import UTC, datetime

    from storage.models import MarketSnapshot

    snaps = [
        MarketSnapshot(
            timestamp=datetime.now(UTC),
            symbol="USDCLP", name="USD/CLP",
            price=900.0, change_pct=1.5, source="yfinance",
        ),
        MarketSnapshot(
            timestamp=datetime.now(UTC),
            symbol="COPPER", name="Cobre",
            price=4.5, change_pct=-0.8, source="yfinance",
        ),
    ]
    html = build_email_html("DMAC", "Resumen", snapshots=snaps)
    assert "USD/CLP" in html
    assert "Cobre" in html
    assert "+1.50%" in html
    assert "-0.80%" in html
    assert "yfinance" in html


def test_build_email_html_skips_deterministic_brief_when_ia_present() -> None:
    """When IA analysis is present and the caller sets
    include_deterministic_brief=False, the parsed "N. Title" sections from
    text_body are omitted from the email body (only the IA card and charts
    remain)."""
    text_body = (
        "1. Resumen ejecutivo\n"
        "* Titular uno\n"
        "* Titular dos\n\n"
        "2. Chile\n"
        "* Hecho Chile\n\n"
        "3. Lectura DMAC\n"
        "* Hechos observados.\n"
    )
    html_no_ia = build_email_html("DMAC", text_body)
    assert "Resumen ejecutivo" in html_no_ia
    assert "Lectura DMAC" in html_no_ia

    nix_html = "<p>Lectura editorial IA de prueba.</p>"
    html_with_ia = build_email_html(
        "DMAC",
        text_body,
        nix_analysis_html=nix_html,
        include_deterministic_brief=False,
    )
    assert "Analisis de Nix" in html_with_ia
    assert "Lectura DMAC" not in html_with_ia
    assert "Resumen ejecutivo" not in html_with_ia
    assert "Lectura editorial IA de prueba." in html_with_ia


def test_build_email_html_ia_card_appears_above_deterministic_sections() -> None:
    """The IA card must appear before the deterministic sections in the HTML."""
    text_body = "1. Resumen ejecutivo\n* x\n"
    nix_html = "<p>IA TLDR.</p>"
    html = build_email_html("DMAC", text_body, nix_analysis_html=nix_html)
    assert html.index("Analisis de Nix") < html.index("Resumen ejecutivo")


def test_build_email_html_omits_ia_charts_for_mvp() -> None:
    """MVP: AI-suggested chart PNGs are accepted but NEVER embedded in the
    productive email. The card keeps the editorial text only."""
    nix_html = "<p>IA editorial.</p>"
    fake_png = b"\x89PNG\r\n\x1a\nfake"
    html = build_email_html(
        "DMAC", "Intro", nix_analysis_html=nix_html,
        nix_chart_pngs={"change_pct_bar": fake_png},
    )
    assert "Analisis de Nix" in html
    assert "IA editorial." in html
    assert "data:image/png;base64," not in html
    assert "Visualizaciones DMAC AI" not in html
    assert "cid:" not in html
