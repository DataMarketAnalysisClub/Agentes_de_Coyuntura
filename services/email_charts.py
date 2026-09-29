"""Static HTML/CSS charts for email.

Plotly charts rely on JavaScript, which most email clients (Gmail, Outlook)
strip entirely. This module renders simple bar charts and data tables using
pure HTML + inline CSS so they survive every email client and look clean.
"""

from __future__ import annotations

from collections import Counter
from html import escape

from services.email_formatter import (
    DMAC_BG,
    DMAC_BORDER,
    DMAC_BRAND_PRIMARY,
    DMAC_BRAND_PRIMARY_DARK,
    DMAC_CARD,
    DMAC_LINK,
    DMAC_MUTED,
    DMAC_TEXT,
    _color_for_change,
    _format_price,
    _normalize_url,
)
from services.market_snapshot import format_as_of
from services.news_charts import NewsChart
from storage.models import MarketSnapshot

_MAX_BAR_WIDTH = 100


def _bar(value: float, max_abs: float, color: str) -> str:
    """Render a single horizontal bar as a div with inline width %."""
    if max_abs <= 0:
        width_pct = 0
    else:
        width_pct = int(round((abs(value) / max_abs) * _MAX_BAR_WIDTH))
    return (
        f'<div style="width: {width_pct}%; background: {color}; height: 10px;'
        f' border-radius: 2px; min-width: 2px;"></div>'
    )


def render_news_distribution_bars(
    news: list,
    *,
    by: str = "region",
    title: str | None = None,
) -> str:
    """Render a horizontal bar chart of news counts grouped by region or topic."""
    if not news:
        return ""

    if by == "topic":
        counts = Counter(n.topic or "macro general" for n in news)
        default_title = "Titulares por tema"
        color = "#7c3aed"
    else:
        counts = Counter(n.region or "Global" for n in news)
        default_title = "Titulares por region"
        color = DMAC_BRAND_PRIMARY

    if not counts:
        return ""

    items = sorted(counts.items(), key=lambda item: item[1], reverse=True)
    max_count = max(counts.values()) or 1
    label = title or default_title

    body_rows: list[str] = []
    for name, count in items:
        body_rows.append(
            "<tr>"
            f"<td style=\"padding: 6px 12px 6px 0; width: 35%; vertical-align: middle;"
            f" color: {DMAC_TEXT}; font-weight: 600; font-size: 12px;\">{escape(name)}</td>"
            f"<td style=\"padding: 6px 8px; width: 45%; vertical-align: middle;\">"
            f"{_bar(float(count), float(max_count), color)}"
            "</td>"
            f"<td style=\"padding: 6px 0 6px 8px; width: 20%; text-align: right; vertical-align: middle;"
            f" color: {DMAC_BRAND_PRIMARY_DARK}; font-weight: 600; font-size: 12px;\">{count}</td>"
            "</tr>"
        )

    return (
        "<tr><td class=\"dmac-px\" style=\"padding: 20px 24px 0 24px;\">"
        f"<h2 style=\"margin: 0 0 12px 0; font-size: 15px; color: {DMAC_BRAND_PRIMARY_DARK};"
        f" letter-spacing: 0.02em; text-transform: uppercase;\">{escape(label)}</h2>"
        "<table role=\"presentation\" cellspacing=\"0\" cellpadding=\"0\" border=\"0\""
        f" style=\"width: 100%; border-collapse: collapse; background: {DMAC_CARD};"
        f" border: 1px solid {DMAC_BORDER}; border-radius: 6px; overflow: hidden;\">"
        f"{''.join(body_rows)}"
        "</table></td></tr>"
    )


# Sparkline de 1 mes: mini grafico de columnas hecho solo con celdas de tabla
# (sin imagenes ni JS). Cada barra es una celda vacia cuyo borde inferior
# tiene el alto de la barra: los bordes se respetan incluso en el motor Word
# de Outlook de escritorio, que ignora el alto de los <div>. Las imagenes
# embebidas (cid: y base64) se veian rotas en Outlook mobile/web (ver
# docs/email-output.md). Cuesta ~1 KB por activo: hay que cuidar el limite de
# ~102 KB sobre el cual Gmail recorta el correo.
_SPARK_MIN_POINTS = 5
_SPARK_HEIGHT_PX = 18
_SPARK_MIN_BAR_PX = 2
_SPARK_WIDTH_PX = 48


def render_sparkline(values: tuple[float, ...] | list[float]) -> str:
    """Render a compact HTML/CSS column sparkline, or '' if there is too little data."""
    return _column_chart(values, width=f"{_SPARK_WIDTH_PX}px", height_px=_SPARK_HEIGHT_PX, spacing=1)


def _column_chart(
    values: tuple[float, ...] | list[float],
    *,
    width: str,
    height_px: int,
    spacing: int,
) -> str:
    points = [float(v) for v in values if v is not None]
    if len(points) < _SPARK_MIN_POINTS:
        return ""

    low, high = min(points), max(points)
    span = high - low
    color = _color_for_change(points[-1] - points[0])
    usable = height_px - _SPARK_MIN_BAR_PX
    cells = []
    for value in points:
        ratio = (value - low) / span if span > 0 else 0.5
        height = _SPARK_MIN_BAR_PX + int(round(ratio * usable))
        cells.append(f'<td style="border-bottom:{height}px solid {color}"></td>')
    change = (points[-1] / points[0] - 1) * 100 if points[0] else 0.0
    label = escape(f"{len(points)} cierres: min {low:,.2f} / max {high:,.2f} ({change:+.1f}%)")
    return (
        f'<table role="img" aria-label="{label}" title="{label}" cellspacing="{spacing}" cellpadding="0"'
        f' border="0" style="width:{width};border-collapse:separate;">'
        f'<tr valign="bottom" style="height:{height_px}px;">{"".join(cells)}</tr></table>'
    )


_FOCUS_CHART_HEIGHT_PX = 56
_FOCUS_MAX_HEADLINES = 2


def render_news_charts_section(charts: list[NewsChart]) -> str:
    """Seccion "En foco": un grafico de 1 mes por activo mencionado en las noticias.

    Cada tarjeta muestra precio, variacion del dia y del periodo, y el o los
    titulares que activaron el grafico (con link a la fuente).
    """
    cards: list[str] = []
    for chart in charts:
        snap = chart.snapshot
        chart_html = _column_chart(snap.history, width="100%", height_px=_FOCUS_CHART_HEIGHT_PX, spacing=2)
        if not chart_html:
            continue
        day_change = "s/d" if snap.change_pct is None else f"{snap.change_pct:+.2f}%"
        period = chart.period_change_pct
        period_text = "" if period is None else f" &middot; {len(snap.history)} cierres: {period:+.1f}%"
        low, high = min(snap.history), max(snap.history)
        headlines = "".join(_focus_headline(item) for item in chart.news[:_FOCUS_MAX_HEADLINES])
        # La lectura es interpretacion de la IA: va rotulada y separada de los datos.
        reading = (
            f"<div style=\"font-size: 12px; color: {DMAC_TEXT}; margin-top: 6px;\">"
            f"<strong style=\"color: {DMAC_BRAND_PRIMARY};\">Lectura de Nix (IA):</strong> {escape(chart.reading)}</div>"
            if chart.reading
            else ""
        )
        cards.append(
            "<tr><td style=\"padding: 12px; border-bottom: 1px solid " + DMAC_BORDER + ";\">"
            "<table role=\"presentation\" cellspacing=\"0\" cellpadding=\"0\" border=\"0\" style=\"width: 100%;\">"
            "<tr>"
            f"<td style=\"font-weight: 600; color: {DMAC_TEXT};\">{escape(snap.name or snap.symbol)}</td>"
            f"<td style=\"text-align: right; color: {DMAC_TEXT};\">{_format_price(snap.price)} "
            f"<span style=\"color: {_color_for_change(snap.change_pct)}; font-weight: 600;\">{day_change}</span></td>"
            "</tr></table>"
            f"<div style=\"font-size: 11px; color: {DMAC_MUTED}; margin: 2px 0 6px 0;\">"
            f"{escape(snap.source or '-')}{period_text} &middot; min {low:,.2f} / max {high:,.2f}</div>"
            f"{chart_html}"
            f"{reading}"
            f"<div style=\"font-size: 11px; color: {DMAC_MUTED}; margin-top: 6px;\">Por la noticia:</div>"
            f"{headlines}"
            "</td></tr>"
        )

    if not cards:
        return ""

    return (
        "<tr><td class=\"dmac-px\" style=\"padding: 20px 24px 0 24px;\">"
        f"<h2 style=\"margin: 0 0 4px 0; font-size: 15px; color: {DMAC_BRAND_PRIMARY_DARK};"
        " letter-spacing: 0.02em; text-transform: uppercase;\">En foco: activos en las noticias</h2>"
        f"<div style=\"margin: 0 0 12px 0; font-size: 12px; color: {DMAC_MUTED};\">"
        "Graficos elegidos segun los titulares de hoy. Ultimo mes de cierres diarios.</div>"
        "<table role=\"presentation\" cellspacing=\"0\" cellpadding=\"0\" border=\"0\""
        f" style=\"width: 100%; border-collapse: collapse; background: {DMAC_CARD};"
        f" border: 1px solid {DMAC_BORDER}; border-radius: 6px; overflow: hidden;\">"
        f"{''.join(cards)}"
        "</table></td></tr>"
    )


def _focus_headline(item) -> str:
    url = _normalize_url(getattr(item, "url", "") or "")
    title = escape(item.title)
    source = escape(item.source or "")
    if url:
        title = (
            f"<a href=\"{escape(url)}\" target=\"_blank\" rel=\"noopener noreferrer\""
            f" style=\"color: {DMAC_LINK}; text-decoration: none;\">{title}</a>"
        )
    return f"<div style=\"font-size: 12px; margin-top: 2px;\">{title} <span style=\"color: {DMAC_MUTED};\">({source})</span></div>"


def render_assets_table(snapshots: list[MarketSnapshot]) -> str:
    """Render a styled HTML table of market snapshots (no Plotly).

    Si hay historia de precios (yfinance), la columna "Fuente" se reemplaza por
    una sparkline de 1 mes. La fuente se indica en una nota al pie ("yfinance
    salvo indicacion") y solo se repite en la fila cuando es otra (BCCh): asi
    la tabla cabe en telefonos de ~320 px sin scroll horizontal.
    """
    rows: list[tuple[str, str, str, str, str]] = []
    with_trend = any(len(snap.history) >= _SPARK_MIN_POINTS for snap in snapshots)
    for snap in snapshots:
        if snap.price is None and snap.change_pct is None:
            continue
        price = _format_table_price(snap.price)
        as_of = format_as_of(snap)
        if as_of:
            # Ultimo dato valido (la fuente no trajo datos hoy): se rotula con
            # su fecha para no presentarlo como precio actual.
            price += f'<div style="font-size: 10px; color: {DMAC_MUTED};">{escape(as_of)}</div>'
        change = "s/d" if snap.change_pct is None else f"{snap.change_pct:+.2f}%"
        change_color = _color_for_change(snap.change_pct)
        source = escape(snap.source or "-")
        symbol = escape(snap.symbol)
        if with_trend:
            if (snap.source or "") != _DEFAULT_TABLE_SOURCE:
                symbol = f"{symbol} &middot; {source}"
            last_cell = render_sparkline(snap.history) or "&nbsp;"
        else:
            last_cell = source
        rows.append((
            escape(snap.name or snap.symbol),
            symbol,
            price,
            f'<span style="color: {change_color}; font-weight: 600;">{change}</span>',
            last_cell,
        ))

    if not rows:
        return (
            "<tr><td class=\"dmac-px\" style=\"padding: 16px 24px; color: " + DMAC_MUTED + ";\">"
            "<em>Mercado cerrado o sin datos disponibles al momento.</em>"
            "</td></tr>"
        )

    last_header = "1 mes" if with_trend else "Fuente"
    header = (
        "<tr style=\"background: " + DMAC_BG + ";\">"
        f"<th style=\"text-align: left; padding: 8px 8px 8px 12px; font-size: 11px; color: {DMAC_MUTED};"
        " text-transform: uppercase; letter-spacing: 0.04em; border-bottom: 1px solid "
        f"{DMAC_BORDER};\">Activo</th>"
        f"<th style=\"text-align: right; padding: 8px; font-size: 11px; color: {DMAC_MUTED};"
        " text-transform: uppercase; letter-spacing: 0.04em; border-bottom: 1px solid "
        f"{DMAC_BORDER};\">Precio</th>"
        f"<th style=\"text-align: right; padding: 8px; font-size: 11px; color: {DMAC_MUTED};"
        " text-transform: uppercase; letter-spacing: 0.04em; border-bottom: 1px solid "
        f"{DMAC_BORDER};\">Var %</th>"
        f"<th style=\"text-align: left; padding: 8px; font-size: 11px; color: {DMAC_MUTED};"
        " text-transform: uppercase; letter-spacing: 0.04em; border-bottom: 1px solid "
        f"{DMAC_BORDER};\">{last_header}</th>"
        "</tr>"
    )

    # Con sparkline se recorta el padding para que la tabla quepa en ~360px.
    last_padding = "8px 8px 8px 4px" if with_trend else "8px"
    body_rows: list[str] = []
    for name, symbol, price, change_html, source in rows:
        body_rows.append(
            "<tr>"
            f"<td style=\"padding: 8px 8px 8px 12px; border-bottom: 1px solid {DMAC_BORDER};\">"
            f"<div style=\"font-weight: 600; color: {DMAC_TEXT};\">{name}</div>"
            f"<div style=\"font-size: 11px; color: {DMAC_MUTED};\">{symbol}</div></td>"
            f"<td style=\"padding: 8px; text-align: right; border-bottom: 1px solid {DMAC_BORDER};"
            f" color: {DMAC_TEXT};\">{price}</td>"
            f"<td style=\"padding: 8px; text-align: right; border-bottom: 1px solid {DMAC_BORDER};\">"
            f"{change_html}</td>"
            f"<td style=\"padding: {last_padding}; border-bottom: 1px solid {DMAC_BORDER};"
            f" color: {DMAC_MUTED}; font-size: 12px;\">{source}</td>"
            "</tr>"
        )

    footnote = (
        f"<div style=\"margin-top: 6px; font-size: 11px; color: {DMAC_MUTED};\">"
        f"Fuente: {_DEFAULT_TABLE_SOURCE} salvo indicacion. 1 mes: cierres diarios.</div>"
        if with_trend
        else ""
    )
    return (
        "<tr><td class=\"dmac-px\" style=\"padding: 16px 24px 0 24px;\">"
        "<table role=\"presentation\" cellspacing=\"0\" cellpadding=\"0\" border=\"0\""
        f" style=\"width: 100%; border-collapse: collapse; background: {DMAC_CARD};"
        f" border: 1px solid {DMAC_BORDER}; border-radius: 6px; overflow: hidden;\">"
        f"{header}{''.join(body_rows)}"
        "</table>"
        f"{footnote}"
        "</td></tr>"
    )


_DEFAULT_TABLE_SOURCE = "yfinance"


def _format_table_price(value: float | None) -> str:
    """Precio para la tabla: sin decimales desde 10.000 (indices) para ahorrar ancho."""
    if value is not None and abs(value) >= 10_000:
        return f"{value:,.0f}"
    return _format_price(value)
