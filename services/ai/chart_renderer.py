"""Deterministic chart rendering with Plotly for the editorial email (phase 3).

Charts are built from already-collected data (snapshots, news). The IA may
suggest chart_specs, but the renderer only trusts chart_type + available data.
Each chart is rendered to a standalone HTML fragment (a <div> with the Plotly
figure and a CDN <script> reference) so it can be embedded in the editorial
email preview HTML and opened in a browser.
"""

from __future__ import annotations

import logging
from html import escape
from pathlib import Path

from services.ai.schemas import AiChartSpec
from storage.models import MarketSnapshot, NewsItem

logger = logging.getLogger(__name__)

try:
    import plotly.graph_objects as go
except ImportError:  # pragma: no cover
    go = None  # type: ignore[assignment]


class ChartRenderError(Exception):
    pass


# Fixed catalog of chart ids that the renderer knows how to build. The editorial
# writer prompt exposes these as AVAILABLE_CHART_IDS. The id is decoupled from
# chart_type so the IA can suggest a chart by stable id.
CHART_CATALOG: dict[str, str] = {
    "impact_ranking_bar": "bar_impact_ranking",
    "news_by_region_bar": "bar_news_by_region",
    "news_by_topic_bar": "bar_news_by_topic",
    "assets_table": "table_assets",
}


def available_chart_ids(
    snapshots: list[MarketSnapshot] | None,
    news: list[NewsItem] | None,
) -> list[str]:
    """Return chart ids that can actually be rendered given the available data."""
    snaps = snapshots or []
    items = news or []
    ids: list[str] = []
    if any(n.impact_score for n in items):
        ids.append("impact_ranking_bar")
    if items:
        ids.append("news_by_region_bar")
        ids.append("news_by_topic_bar")
    if snaps:
        ids.append("assets_table")
    return ids


def render_chart_to_html(
    spec: AiChartSpec,
    snapshots: list[MarketSnapshot] | None = None,
    news: list[NewsItem] | None = None,
) -> str:
    """Render a single chart spec to an HTML fragment (div + plotly CDN script)."""
    if go is None:
        raise ChartRenderError("plotly is not installed")

    fig = _build_figure(spec, snapshots or [], news or [])

    return fig.to_html(
        full_html=False,
        include_plotlyjs="cdn",
        div_id=f"chart_{escape(spec.chart_id)}",
        config={"displayModeBar": False},
    )


def render_charts(
    specs: list[AiChartSpec],
    snapshots: list[MarketSnapshot] | None = None,
    news: list[NewsItem] | None = None,
    output_dir: Path | None = None,
) -> dict[str, str]:
    """Render a list of chart specs to HTML fragments.

    Returns a dict mapping chart_id -> html fragment. If output_dir is given,
    each chart is also saved as a standalone .html file named {chart_id}.html.
    """
    fragments: dict[str, str] = {}
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)

    for spec in specs:
        try:
            html = render_chart_to_html(spec, snapshots, news)
        except ChartRenderError as e:
            logger.warning("Chart %s skipped: %s", spec.chart_id, e)
            continue
        fragments[spec.chart_id] = html
        if output_dir is not None:
            (output_dir / f"{spec.chart_id}.html").write_text(
                _wrap_standalone(html, spec.title),
                encoding="utf-8",
            )
    return fragments


def _wrap_standalone(fragment: str, title: str) -> str:
    return (
        "<!doctype html>\n"
        '<html lang="es">\n<head>\n'
        '<meta charset="utf-8">\n'
        f"<title>{escape(title)}</title>\n"
        "</head>\n<body>\n"
        f"{fragment}\n"
        "</body>\n</html>"
    )


def render_charts_as_png(
    specs: list[AiChartSpec],
    snapshots: list[MarketSnapshot] | None = None,
    news: list[NewsItem] | None = None,
    scale: float = 2.0,
) -> dict[str, bytes]:
    """Render chart specs to PNG bytes via kaleido for email embedding.

    Returns a dict mapping chart_id -> PNG bytes. Skips specs that cannot be
    rendered (unknown type, no data, missing kaleido, etc.) and logs a warning.
    Plotly + kaleido must be importable; otherwise the function returns an
    empty dict and logs a single warning.
    """
    pngs: dict[str, bytes] = {}
    if go is None:
        logger.warning("Plotly not installed; PNG charts skipped")
        return pngs

    for spec in specs:
        try:
            fig = _build_figure(spec, snapshots or [], news or [])
            png_bytes = fig.to_image(format="png", engine="kaleido", scale=scale)
        except ChartRenderError as e:
            logger.warning("Chart %s skipped: %s", spec.chart_id, e)
            continue
        except Exception as e:  # noqa: BLE001
            logger.warning(
                "Chart %s PNG render failed: %s", spec.chart_id, e,
            )
            continue
        pngs[spec.chart_id] = png_bytes
    return pngs


def _build_figure(
    spec: AiChartSpec,
    snapshots: list[MarketSnapshot],
    news: list[NewsItem],
):
    """Build the Plotly figure for a spec, raising ChartRenderError on failure."""
    if spec.chart_type == "bar_change_pct":
        return _build_change_pct_bar(spec, snapshots)
    if spec.chart_type == "bar_impact_ranking":
        return _build_impact_ranking(spec, news)
    if spec.chart_type == "bar_news_by_region":
        return _build_news_by_region(spec, news)
    if spec.chart_type == "bar_news_by_topic":
        return _build_news_by_topic(spec, news)
    if spec.chart_type == "table_assets":
        return _build_assets_table(spec, snapshots)
    raise ChartRenderError(f"Unknown chart type: {spec.chart_type}")


def _apply_layout(fig: go.Figure, spec: AiChartSpec) -> go.Figure:
    fig.update_layout(
        title={"text": spec.title, "x": 0.05, "xanchor": "left"},
        margin={"l": 40, "r": 20, "t": 50, "b": 40},
        font={"family": "Arial, sans-serif", "size": 12, "color": "#111827"},
        plot_bgcolor="#ffffff",
        paper_bgcolor="#ffffff",
    )
    if spec.subtitle:
        fig.update_layout(annotations=[{
            "text": spec.subtitle,
            "xref": "paper",
            "yref": "paper",
            "x": 0.05,
            "y": 1.0,
            "showarrow": False,
            "font": {"size": 11, "color": "#6b7280"},
            "yanchor": "bottom",
        }])
    return fig


def _build_change_pct_bar(spec: AiChartSpec, snapshots: list[MarketSnapshot]) -> go.Figure:
    rows = [
        (s.name or s.symbol, s.change_pct)
        for s in snapshots
        if s.change_pct is not None
    ]
    if not rows:
        raise ChartRenderError("no snapshots with change_pct")
    rows.sort(key=lambda r: r[1] or 0.0)
    labels = [r[0] for r in rows]
    values = [r[1] or 0.0 for r in rows]
    colors = ["#dc2626" if v < 0 else "#16a34a" for v in values]
    fig = go.Figure(data=[go.Bar(x=values, y=labels, orientation="h", marker_color=colors)])
    fig.update_xaxes(title_text="Variacion %")
    return _apply_layout(fig, spec)


def _build_impact_ranking(spec: AiChartSpec, news: list[NewsItem]) -> go.Figure:
    rows = [(n.title, n.impact_score) for n in news if n.impact_score > 0]
    if not rows:
        raise ChartRenderError("no news with impact_score > 0")
    rows.sort(key=lambda r: r[1], reverse=True)
    top = rows[:10]
    labels = [_truncate(t, 60) for t, _ in top][::-1]
    values = [v for _, v in top][::-1]
    fig = go.Figure(data=[go.Bar(x=values, y=labels, orientation="h", marker_color="#1d4ed8")])
    fig.update_xaxes(title_text="Impacto")
    return _apply_layout(fig, spec)


def _build_news_by_region(spec: AiChartSpec, news: list[NewsItem]) -> go.Figure:
    from collections import Counter

    counts = Counter(n.region or "Global" for n in news)
    if not counts:
        raise ChartRenderError("no news to count by region")
    labels = list(counts.keys())
    values = list(counts.values())
    fig = go.Figure(data=[go.Bar(x=labels, y=values, marker_color="#0891b2")])
    fig.update_yaxes(title_text="Noticias")
    return _apply_layout(fig, spec)


def _build_news_by_topic(spec: AiChartSpec, news: list[NewsItem]) -> go.Figure:
    from collections import Counter

    counts = Counter(n.topic or "macro general" for n in news)
    if not counts:
        raise ChartRenderError("no news to count by topic")
    labels = list(counts.keys())
    values = list(counts.values())
    fig = go.Figure(data=[go.Bar(x=labels, y=values, marker_color="#7c3aed")])
    fig.update_yaxes(title_text="Noticias")
    return _apply_layout(fig, spec)


def _build_assets_table(spec: AiChartSpec, snapshots: list[MarketSnapshot]) -> go.Figure:
    if not snapshots:
        raise ChartRenderError("no snapshots for assets table")
    header = ["Activo", "Simbolo", "Precio", "Var %", "Fuente"]
    rows = []
    for s in sorted(snapshots, key=lambda x: x.symbol):
        price = f"{s.price:.2f}" if s.price is not None else "-"
        change = f"{s.change_pct:+.2f}%" if s.change_pct is not None else "-"
        rows.append([s.name or s.symbol, s.symbol, price, change, s.source])
    fig = go.Figure(data=[go.Table(
        header={"values": header, "fill_color": "#f3f4f6", "font": {"color": "#111827", "size": 12}},
        cells={"values": list(map(list, zip(*rows))), "fill_color": "#ffffff", "font": {"color": "#111827", "size": 11}},
    )])
    return _apply_layout(fig, spec)


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "\u2026"
