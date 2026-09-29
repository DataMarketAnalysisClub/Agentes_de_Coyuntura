from datetime import UTC, datetime

from services.email_charts import render_news_charts_section
from services.email_formatter import build_email_html
from services.news_charts import assets_mentioned, select_news_charts
from storage.models import MarketSnapshot, NewsItem

NOW = datetime(2026, 9, 28, 12, tzinfo=UTC)
HISTORY = (100.0, 101.0, 99.0, 102.0, 103.0, 104.0)


def _news(title: str, summary: str = "", impact: int = 5, url: str = "https://example.com/n") -> NewsItem:
    return NewsItem(NOW, "La Tercera Pulso", title, url, summary, "Chile", "commodities", impact)


def _snap(symbol: str, name: str, history: tuple[float, ...] = HISTORY, change: float = 0.5) -> MarketSnapshot:
    return MarketSnapshot(NOW, symbol, name, history[-1] if history else 1.0, change, "yfinance", history=history)


SNAPSHOTS = [
    _snap("USDCLP", "USD/CLP"),
    _snap("COPPER", "Cobre", change=-1.3),
    _snap("IPSA", "IPSA"),
    _snap("GOLD", "Oro"),
    _snap("BRENT", "Brent"),
    MarketSnapshot(NOW, "TPM", "TPM Chile", 4.75, None, "bcentral"),
]


class TestAssetsMentioned:
    def test_detects_copper_and_chilean_peso(self) -> None:
        mentions = assets_mentioned(_news("Cobre cae y el peso chileno se debilita frente al dólar"))
        assert set(mentions) == {"COPPER", "USDCLP"}

    def test_title_weighs_more_than_summary(self) -> None:
        mentions = assets_mentioned(_news("Codelco reporta resultados", summary="El IPSA subio 1%"))
        assert mentions["COPPER"] > mentions["IPSA"]

    def test_uses_word_boundaries(self) -> None:
        text = "Market turmoil hits the Tesoro and a golden week for SEC filings"
        assert assets_mentioned(_news(text)) == {}

    def test_mexican_inflation_ipc_is_not_an_asset(self) -> None:
        assert assets_mentioned(_news("IPC de Mexico sube mas de lo esperado")) == {}

    def test_english_dollar_is_dxy_and_spanish_dolar_is_usdclp(self) -> None:
        assert set(assets_mentioned(_news("Dollar holds near two-month peak"))) == {"DXY"}
        assert set(assets_mentioned(_news("Dolar cierra al alza"))) == {"USDCLP"}

    def test_copper_mine_news_maps_to_copper(self) -> None:
        assert "COPPER" in assets_mentioned(_news("Sindicatos de Minera Centinela aprueban huelga"))

    def test_spanish_bonos_are_not_treasuries(self) -> None:
        assert assets_mentioned(_news("Gobierno emite bonos soberanos en francos suizos")) == {}
        assert "US10Y" in assets_mentioned(_news("Stocks wobble as bonds slump"))

    def test_symbols_with_punctuation(self) -> None:
        mentions = assets_mentioned(_news("S&P 500 y USD/CLP en maximos"))
        assert {"SP500", "USDCLP"} <= set(mentions)


class TestSelectNewsCharts:
    def test_charts_follow_the_news(self) -> None:
        news = [_news("Cobre cae 2% por temor a China"), _news("Dolar sube a $970 en Chile")]

        charts = select_news_charts(news, SNAPSHOTS)

        assert [c.snapshot.symbol for c in charts] == ["COPPER", "USDCLP"]
        assert charts[0].news[0].title.startswith("Cobre")

    def test_asset_mentioned_by_more_news_ranks_first(self) -> None:
        news = [
            _news("Oro marca record"),
            _news("Dolar sube en Chile"),
            _news("El dolar cierra en maximos"),
        ]

        charts = select_news_charts(news, SNAPSHOTS)

        assert charts[0].snapshot.symbol == "USDCLP"
        assert len(charts[0].news) == 2

    def test_no_mentions_means_no_charts(self) -> None:
        assert select_news_charts([_news("Gobierno presenta plan de empleo")], SNAPSHOTS) == []

    def test_assets_without_history_are_not_charted(self) -> None:
        snapshots = [_snap("COPPER", "Cobre", history=(1.0, 2.0))]
        assert select_news_charts([_news("Cobre sube")], snapshots) == []

    def test_respects_max_charts(self) -> None:
        news = [_news("Cobre, oro, petroleo y dolar se mueven; IPSA cae")]
        assert len(select_news_charts(news, SNAPSHOTS, max_charts=2)) == 2
        assert select_news_charts(news, SNAPSHOTS, max_charts=0) == []


class TestRenderNewsCharts:
    def test_section_cites_the_triggering_headline(self) -> None:
        charts = select_news_charts([_news("Cobre cae 2%", url="https://example.com/cobre")], SNAPSHOTS)

        html = render_news_charts_section(charts)

        assert "En foco" in html
        assert "Cobre" in html
        assert 'href="https://example.com/cobre"' in html
        assert html.count('<td style="border-bottom:') == len(HISTORY)
        assert "+4,0%" in html  # variacion del periodo 100 -> 104

    def test_empty_selection_renders_nothing(self) -> None:
        assert render_news_charts_section([]) == ""

    def test_email_includes_focus_section_only_when_news_mention_assets(self) -> None:
        with_asset = build_email_html(
            "Brief", "Intro", snapshots=SNAPSHOTS, news_items=[_news("Cobre cae 2%")]
        )
        without_asset = build_email_html(
            "Brief", "Intro", snapshots=SNAPSHOTS, news_items=[_news("Plan de empleo")]
        )

        assert "En foco" in with_asset
        assert "En foco" not in without_asset
