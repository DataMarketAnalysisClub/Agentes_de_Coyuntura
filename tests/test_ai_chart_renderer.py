from datetime import UTC, datetime

import pytest

from services.ai.chart_renderer import (
    ChartRenderError,
    available_chart_ids,
    render_chart_to_html,
    render_charts,
    render_charts_as_png,
)
from services.ai.schemas import AiChartSpec
from storage.models import MarketSnapshot, NewsItem


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
        MarketSnapshot(
            timestamp=datetime.now(UTC),
            symbol="IPSA",
            name="IPSA",
            price=5000.0,
            change_pct=-0.3,
            source="yfinance",
        ),
    ]


def _make_news(count: int = 5) -> list[NewsItem]:
    return [
        NewsItem(
            timestamp=datetime.now(UTC),
            source=f"Source {i}",
            title=f"Title {i}",
            url=f"https://example.com/{i}",
            summary=f"Summary {i}",
            region="Chile" if i % 2 == 0 else "EE.UU.",
            topic="tasas" if i % 2 == 0 else "commodities",
            impact_score=10 - i,
        )
        for i in range(count)
    ]


class TestChartRenderer:
    def test_available_chart_ids_with_full_data(self) -> None:
        ids = available_chart_ids(_make_snapshots(), _make_news())
        assert "change_pct_bar" not in ids
        assert "impact_ranking_bar" in ids
        assert "news_by_region_bar" in ids
        assert "news_by_topic_bar" in ids
        assert "assets_table" in ids

    def test_available_chart_ids_empty(self) -> None:
        ids = available_chart_ids([], [])
        assert ids == []

    def test_available_chart_ids_no_change_pct(self) -> None:
        snaps = [MarketSnapshot(
            timestamp=datetime.now(UTC),
            symbol="X",
            name="X",
            price=1.0,
            change_pct=None,
            source="yfinance",
        )]
        ids = available_chart_ids(snaps, [])
        assert "change_pct_bar" not in ids
        assert "assets_table" in ids

    def test_render_change_pct_bar(self) -> None:
        spec = AiChartSpec(
            chart_id="change_pct_bar",
            chart_type="bar_change_pct",
            title="Variacion %",
        )
        html = render_chart_to_html(spec, _make_snapshots(), [])
        assert "plotly" in html.lower()
        assert "IPSA" in html

    def test_render_impact_ranking(self) -> None:
        spec = AiChartSpec(
            chart_id="impact_ranking_bar",
            chart_type="bar_impact_ranking",
            title="Ranking",
        )
        html = render_chart_to_html(spec, [], _make_news())
        assert "plotly" in html.lower()

    def test_render_news_by_region(self) -> None:
        spec = AiChartSpec(
            chart_id="news_by_region_bar",
            chart_type="bar_news_by_region",
            title="Por region",
        )
        html = render_chart_to_html(spec, [], _make_news())
        assert "plotly" in html.lower()
        assert "Chile" in html

    def test_render_news_by_topic(self) -> None:
        spec = AiChartSpec(
            chart_id="news_by_topic_bar",
            chart_type="bar_news_by_topic",
            title="Por topic",
        )
        html = render_chart_to_html(spec, [], _make_news())
        assert "plotly" in html.lower()
        assert "tasas" in html

    def test_render_assets_table(self) -> None:
        spec = AiChartSpec(
            chart_id="assets_table",
            chart_type="table_assets",
            title="Activos",
        )
        html = render_chart_to_html(spec, _make_snapshots(), [])
        assert "plotly" in html.lower()
        assert "USDCLP" in html

    def test_render_unknown_type_raises(self) -> None:
        spec = AiChartSpec(
            chart_id="x",
            chart_type="bar_change_pct",
            title="x",
        )
        spec = spec.model_copy(update={"chart_type": "bar_change_pct"})
        # Manually break chart_type to bypass Literal validation
        object.__setattr__(spec, "chart_type", "unknown")
        with pytest.raises(ChartRenderError):
            render_chart_to_html(spec, [], [])

    def test_render_change_pct_no_data_raises(self) -> None:
        spec = AiChartSpec(
            chart_id="change_pct_bar",
            chart_type="bar_change_pct",
            title="x",
        )
        with pytest.raises(ChartRenderError):
            render_chart_to_html(spec, [], [])

    def test_render_charts_returns_dict(self) -> None:
        specs = [
            AiChartSpec(chart_id="change_pct_bar", chart_type="bar_change_pct", title="A"),
            AiChartSpec(chart_id="impact_ranking_bar", chart_type="bar_impact_ranking", title="B"),
        ]
        fragments = render_charts(specs, _make_snapshots(), _make_news())
        assert set(fragments.keys()) == {"change_pct_bar", "impact_ranking_bar"}

    def test_render_charts_skips_failed(self) -> None:
        good = AiChartSpec(chart_id="change_pct_bar", chart_type="bar_change_pct", title="A")
        bad = AiChartSpec(chart_id="impact_ranking_bar", chart_type="bar_impact_ranking", title="B")
        fragments = render_charts([good, bad], _make_snapshots(), [])
        assert "change_pct_bar" in fragments
        assert "impact_ranking_bar" not in fragments

    def test_render_charts_as_png_returns_bytes(self) -> None:
        spec = AiChartSpec(
            chart_id="change_pct_bar",
            chart_type="bar_change_pct",
            title="Variacion",
        )
        pngs = render_charts_as_png([spec], _make_snapshots(), [])
        if pngs:
            assert isinstance(pngs["change_pct_bar"], bytes)
            assert pngs["change_pct_bar"].startswith(b"\x89PNG")

    def test_render_charts_as_png_skips_failed(self) -> None:
        good = AiChartSpec(chart_id="change_pct_bar", chart_type="bar_change_pct", title="A")
        bad = AiChartSpec(chart_id="impact_ranking_bar", chart_type="bar_impact_ranking", title="B")
        pngs = render_charts_as_png([good, bad], _make_snapshots(), [])
        assert "change_pct_bar" in pngs
        assert "impact_ranking_bar" not in pngs
