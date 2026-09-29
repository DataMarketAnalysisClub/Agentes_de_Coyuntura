import json
from datetime import UTC, datetime

from app.config import Settings
from services.ai.news_chart_readings import (
    generate_chart_readings,
    select_news_charts_with_readings,
)
from services.ai.ollama_client import OllamaCloudError
from services.email_charts import render_news_charts_section
from storage.models import MarketSnapshot, NewsItem

NOW = datetime(2026, 9, 28, 12, tzinfo=UTC)
HISTORY = (100.0, 101.0, 99.0, 102.0, 103.0, 104.0)
SNAPSHOTS = [
    MarketSnapshot(NOW, "COPPER", "Cobre", 104.0, -1.3, "yfinance", history=HISTORY),
    MarketSnapshot(NOW, "USDCLP", "USD/CLP", 104.0, 0.4, "yfinance", history=HISTORY),
    MarketSnapshot(NOW, "GOLD", "Oro", 104.0, 0.1, "yfinance", history=HISTORY),
]
NEWS = [NewsItem(NOW, "DF", "Cobre cae por huelga en Centinela", "https://example.com/c", "", "Chile", "commodities", 7)]
AI_SETTINGS = Settings(ai_enabled=True, ai_brief_enabled=True, ai_dry_run=False)


class FakeClient:
    def __init__(self, response: str | Exception, settings: Settings = AI_SETTINGS) -> None:
        self.response = response
        self.settings = settings
        self.prompts: list[str] = []

    def chat_json(self, system_prompt: str, user_prompt: str) -> str:
        self.prompts.append(user_prompt)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _readings(*items: tuple[str, str]) -> str:
    return json.dumps({"readings": [{"symbol": symbol, "reading": text} for symbol, text in items]})


def test_readings_are_attached_only_to_deterministic_candidates() -> None:
    client = FakeClient(
        _readings(
            ("COPPER", "La caida del cobre coincide con la huelga en Centinela."),
            ("GOLD", "El oro sube como refugio."),  # ninguna noticia menciona oro
        )
    )

    charts = select_news_charts_with_readings(NEWS, SNAPSHOTS, AI_SETTINGS, client=client)

    assert [chart.snapshot.symbol for chart in charts] == ["COPPER"]
    assert charts[0].reading == "La caida del cobre coincide con la huelga en Centinela."
    # El prompt solo expone los candidatos, con sus titulares.
    assert '"symbol": "COPPER"' in client.prompts[0]
    assert "GOLD" not in client.prompts[0]


def test_ai_disabled_returns_charts_without_calling_client() -> None:
    client = FakeClient(_readings(("COPPER", "x")))

    charts = select_news_charts_with_readings(NEWS, SNAPSHOTS, Settings(ai_enabled=False), client=client)

    assert [chart.reading for chart in charts] == [""]
    assert client.prompts == []


def test_ai_failure_or_invalid_json_keeps_charts_without_reading() -> None:
    for response in (OllamaCloudError("down"), "not json", json.dumps({"readings": "bad"})):
        charts = select_news_charts_with_readings(NEWS, SNAPSHOTS, AI_SETTINGS, client=FakeClient(response))
        assert [(chart.snapshot.symbol, chart.reading) for chart in charts] == [("COPPER", "")]


def test_unexpected_error_does_not_break_selection() -> None:
    charts = select_news_charts_with_readings(NEWS, SNAPSHOTS, AI_SETTINGS, client=FakeClient(RuntimeError("boom")))

    assert [chart.reading for chart in charts] == [""]


def test_readings_with_investment_advice_or_too_long_are_dropped() -> None:
    charts = select_news_charts_with_readings(NEWS, SNAPSHOTS, AI_SETTINGS, client=FakeClient("{}"))
    client = FakeClient(_readings(("COPPER", "Buen momento para comprar cobre.")))
    assert generate_chart_readings(charts, client) == {}
    client = FakeClient(_readings(("COPPER", "x" * 300)))
    assert generate_chart_readings(charts, client) == {}


def test_dry_run_stub_yields_no_readings() -> None:
    settings = Settings(ai_enabled=True, ai_brief_enabled=True, ai_dry_run=True)

    charts = select_news_charts_with_readings(NEWS, SNAPSHOTS, settings)

    assert [chart.reading for chart in charts] == [""]


def test_render_shows_labeled_reading_escaped() -> None:
    client = FakeClient(_readings(("COPPER", "Cobre <cae> en medio de la huelga.")))
    charts = select_news_charts_with_readings(NEWS, SNAPSHOTS, AI_SETTINGS, client=client)

    html = render_news_charts_section(charts)

    assert "Lectura de Nix (IA):" in html
    assert "Cobre &lt;cae&gt; en medio de la huelga." in html
    assert html.index("Lectura de Nix") < html.index("Por la noticia")


def test_render_without_reading_has_no_label() -> None:
    charts = select_news_charts_with_readings(NEWS, SNAPSHOTS, Settings(ai_enabled=False))

    assert "Lectura de Nix" not in render_news_charts_section(charts)


def test_build_email_html_uses_precomputed_news_charts() -> None:
    from services.email_formatter import build_email_html

    client = FakeClient(_readings(("COPPER", "Lectura precalculada.")))
    charts = select_news_charts_with_readings(NEWS, SNAPSHOTS, AI_SETTINGS, client=client)

    html = build_email_html("Asunto", "", snapshots=SNAPSHOTS, news_items=NEWS, news_charts=charts)

    assert "Lectura precalculada." in html
