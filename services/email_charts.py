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


def render_assets_table(snapshots: list[MarketSnapshot]) -> str:
    """Render a styled HTML table of market snapshots (no Plotly)."""
    rows: list[tuple[str, str, str, str, str]] = []
    for snap in snapshots:
        if snap.price is None and snap.change_pct is None:
            continue
        price = _format_price(snap.price)
        change = "s/d" if snap.change_pct is None else f"{snap.change_pct:+.2f}%"
        change_color = _color_for_change(snap.change_pct)
        rows.append((
            escape(snap.name or snap.symbol),
            escape(snap.symbol),
            price,
            f'<span style="color: {change_color}; font-weight: 600;">{change}</span>',
            escape(snap.source or "-"),
        ))

    if not rows:
        return (
            "<tr><td style=\"padding: 16px 24px; color: " + DMAC_MUTED + ";\">"
            "<em>Mercado cerrado o sin datos disponibles al momento.</em>"
            "</td></tr>"
        )

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
        f"{DMAC_BORDER};\">Fuente</th>"
        "</tr>"
    )

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
            f"<td style=\"padding: 8px 12px; border-bottom: 1px solid {DMAC_BORDER};"
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
