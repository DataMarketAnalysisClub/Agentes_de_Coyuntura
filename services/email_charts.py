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
    DMAC_MUTED,
    DMAC_TEXT,
    _color_for_change,
    _format_price,
)
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
        "<tr><td style=\"padding: 20px 24px 0 24px;\">"
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
_SPARK_WIDTH_PX = 60


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


def render_assets_table(snapshots: list[MarketSnapshot]) -> str:
    """Render a styled HTML table of market snapshots (no Plotly).

    Si hay historia de precios (yfinance), la columna "Fuente" se reemplaza por
    una sparkline de 1 mes y la fuente pasa a la linea secundaria del activo,
    para no agregar una quinta columna que desborde en pantallas de telefono.
    """
    rows: list[tuple[str, str, str, str, str]] = []
    with_trend = any(len(snap.history) >= _SPARK_MIN_POINTS for snap in snapshots)
    for snap in snapshots:
        if snap.price is None and snap.change_pct is None:
            continue
        price = _format_price(snap.price)
        change = "s/d" if snap.change_pct is None else f"{snap.change_pct:+.2f}%"
        change_color = _color_for_change(snap.change_pct)
        source = escape(snap.source or "-")
        symbol = escape(snap.symbol)
        if with_trend:
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
            "<tr><td style=\"padding: 16px 24px; color: " + DMAC_MUTED + ";\">"
            "<em>Mercado cerrado o sin datos disponibles al momento.</em>"
            "</td></tr>"
        )

    last_header = "1 mes" if with_trend else "Fuente"
    header = (
        "<tr style=\"background: " + DMAC_BG + ";\">"
        f"<th style=\"text-align: left; padding: 8px 12px; font-size: 11px; color: {DMAC_MUTED};"
        " text-transform: uppercase; letter-spacing: 0.04em; border-bottom: 1px solid "
        f"{DMAC_BORDER};\">Activo</th>"
        f"<th style=\"text-align: right; padding: 8px 12px; font-size: 11px; color: {DMAC_MUTED};"
        " text-transform: uppercase; letter-spacing: 0.04em; border-bottom: 1px solid "
        f"{DMAC_BORDER};\">Precio</th>"
        f"<th style=\"text-align: right; padding: 8px 12px; font-size: 11px; color: {DMAC_MUTED};"
        " text-transform: uppercase; letter-spacing: 0.04em; border-bottom: 1px solid "
        f"{DMAC_BORDER};\">Var %</th>"
        f"<th style=\"text-align: left; padding: 8px 12px; font-size: 11px; color: {DMAC_MUTED};"
        " text-transform: uppercase; letter-spacing: 0.04em; border-bottom: 1px solid "
        f"{DMAC_BORDER};\">{last_header}</th>"
        "</tr>"
    )

    # Con sparkline se recorta el padding para que la tabla quepa en ~360px.
    last_padding = "8px 8px 8px 4px" if with_trend else "8px 12px"
    body_rows: list[str] = []
    for name, symbol, price, change_html, source in rows:
        body_rows.append(
            "<tr>"
            f"<td style=\"padding: 8px 12px; border-bottom: 1px solid {DMAC_BORDER};\">"
            f"<div style=\"font-weight: 600; color: {DMAC_TEXT};\">{name}</div>"
            f"<div style=\"font-size: 11px; color: {DMAC_MUTED};\">{symbol}</div></td>"
            f"<td style=\"padding: 8px 12px; text-align: right; border-bottom: 1px solid {DMAC_BORDER};"
            f" color: {DMAC_TEXT};\">{price}</td>"
            f"<td style=\"padding: 8px 12px; text-align: right; border-bottom: 1px solid {DMAC_BORDER};\">"
            f"{change_html}</td>"
            f"<td style=\"padding: {last_padding}; border-bottom: 1px solid {DMAC_BORDER};"
            f" color: {DMAC_MUTED}; font-size: 12px;\">{source}</td>"
            "</tr>"
        )

    return (
        "<tr><td style=\"padding: 16px 24px 0 24px;\">"
        "<table role=\"presentation\" cellspacing=\"0\" cellpadding=\"0\" border=\"0\""
        f" style=\"width: 100%; border-collapse: collapse; background: {DMAC_CARD};"
        f" border: 1px solid {DMAC_BORDER}; border-radius: 6px; overflow: hidden;\">"
        f"{header}{''.join(body_rows)}"
        "</table></td></tr>"
    )
