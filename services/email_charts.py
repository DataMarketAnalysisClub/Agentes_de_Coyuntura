"""Static HTML/CSS charts and market table for email.

Plotly charts rely on JavaScript, which most email clients (Gmail, Outlook)
strip entirely. This module renders column charts and data tables using
pure HTML + inline CSS so they survive every email client.
"""

from __future__ import annotations

from collections import Counter
from html import escape

from services.email_formatter import (
    CONTENT_WIDTH_PX,
    DMAC_BRAND_PRIMARY,
    DMAC_INK,
    DMAC_MUTED,
    DMAC_RULE_SOFT,
    DMAC_SERIF,
    DMAC_TEXT,
    _color_for_change,
    _format_change,
    _normalize_url,
    _section_row,
    fluid_columns,
    format_number,
    section_eyebrow,
)
from services.market_snapshot import format_as_of
from services.news_charts import NewsChart
from storage.models import MarketSnapshot

# Rendimientos: el nivel ya es un %, y su cambio se expresa en puntos base
# (0,13% de 5,25 es +0,7 pb, no "+0,13%").
YIELD_SYMBOLS = frozenset({"US10Y"})
# Indicadores que son tasas o porcentajes: se muestran con "%" y los
# decimales indicados.
PERCENT_LEVEL_DECIMALS = {"TPM": 2, "IPC": 1, "DESEMPLEO": 1}

# Grupos de la tabla de mercados, en orden de lectura para un lector chileno.
# Un simbolo que no aparece aqui va al final, en "Otros".
MARKET_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Chile", ("USDCLP", "IPSA", "TPM", "IPC", "DESEMPLEO")),
    ("Estados Unidos", ("SP500", "VOO", "NASDAQ100", "US10Y", "DXY")),
    ("Materias primas", ("COPPER", "GOLD", "WTI", "BRENT")),
    ("Resto del mundo", ("EUROSTOXX50", "BOVESPA", "MEXIPC", "USDBRL", "USDMXN", "USDCOP", "USDPEN")),
)

_DEFAULT_TABLE_SOURCE = "yfinance"
_SOURCE_LABELS = {"yfinance": "Yahoo Finance", "bcentral": "BCCh"}
_MAX_BAR_WIDTH = 100


def format_snapshot_value(snap: MarketSnapshot) -> str:
    """Nivel del activo: 970,93 · 11.133 · 5,25% (tasas) · 9,5% (desempleo)."""
    if snap.price is None:
        return "-"
    if snap.symbol in YIELD_SYMBOLS:
        return f"{format_number(snap.price, 2)}%"
    if snap.symbol in PERCENT_LEVEL_DECIMALS:
        return f"{format_number(snap.price, PERCENT_LEVEL_DECIMALS[snap.symbol])}%"
    if abs(snap.price) >= 10_000:
        # Indices: sin decimales para ahorrar ancho en telefonos.
        return format_number(snap.price, 0)
    return format_number(snap.price, 2)


def format_snapshot_change(snap: MarketSnapshot) -> tuple[str, str]:
    """(texto, color) de la variacion del dia; en pb para rendimientos."""
    if snap.change_pct is None:
        return ("s/d" if snap.symbol not in PERCENT_LEVEL_DECIMALS else "", _color_for_change(None))
    color = _color_for_change(snap.change_pct)
    if snap.symbol in YIELD_SYMBOLS and snap.price is not None:
        previous = snap.price / (1 + snap.change_pct / 100)
        basis_points = (snap.price - previous) * 100
        sign = "+" if basis_points >= 0 else ""
        return (f"{sign}{format_number(basis_points, 1)} pb", color)
    return (_format_change(snap.change_pct), color)


def _bar(value: float, max_abs: float, color: str) -> str:
    """Render a single horizontal bar as a div with inline width %."""
    width_pct = 0 if max_abs <= 0 else int(round((abs(value) / max_abs) * _MAX_BAR_WIDTH))
    return (
        f'<div style="width: {width_pct}%; background: {color}; height: 10px;'
        f' min-width: 2px;"></div>'
    )


def render_news_distribution_bars(
    news: list,
    *,
    by: str = "region",
    title: str | None = None,
) -> str:
    """Barras horizontales con la cantidad de titulares por region o tema.

    Ya no va en el correo (con 3 titulares no aportaba); se conserva para
    reportes con mas noticias.
    """
    if not news:
        return ""
    if by == "topic":
        counts = Counter(n.topic or "macro general" for n in news)
        default_title = "Titulares por tema"
    else:
        counts = Counter(n.region or "Global" for n in news)
        default_title = "Titulares por región"
    if not counts:
        return ""

    max_count = max(counts.values()) or 1
    body_rows = "".join(
        "<tr>"
        f"<td style=\"padding: 6px 12px 6px 0; width: 35%; color: {DMAC_TEXT}; font-weight: 600; font-size: 13px;\">"
        f"{escape(name)}</td>"
        f"<td style=\"padding: 6px 8px; width: 50%;\">{_bar(float(count), float(max_count), DMAC_BRAND_PRIMARY)}</td>"
        f"<td style=\"padding: 6px 0; width: 15%; text-align: right; font-size: 13px; color: {DMAC_INK};\">{count}</td>"
        "</tr>"
        for name, count in sorted(counts.items(), key=lambda item: item[1], reverse=True)
    )
    return _section_row(
        section_eyebrow(title or default_title)
        + "<table role=\"presentation\" cellspacing=\"0\" cellpadding=\"0\" border=\"0\" width=\"100%\">"
        + body_rows
        + "</table>"
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
    color: str | None = None,
) -> str:
    points = [float(v) for v in values if v is not None]
    if len(points) < _SPARK_MIN_POINTS:
        return ""

    low, high = min(points), max(points)
    span = high - low
    bar_color = color or _color_for_change(points[-1] - points[0])
    usable = height_px - _SPARK_MIN_BAR_PX
    cells = []
    for value in points:
        ratio = (value - low) / span if span > 0 else 0.5
        height = _SPARK_MIN_BAR_PX + int(round(ratio * usable))
        cells.append(f'<td style="border-bottom:{height}px solid {bar_color}"></td>')
    change = (points[-1] / points[0] - 1) * 100 if points[0] else 0.0
    label = escape(
        f"{len(points)} cierres: mín. {format_number(low)} / máx. {format_number(high)}"
        f" ({'+' if change >= 0 else ''}{format_number(change, 1)}%)"
    )
    return (
        f'<table role="img" aria-label="{label}" title="{label}" cellspacing="{spacing}" cellpadding="0"'
        f' border="0" style="width:{width};border-collapse:separate;">'
        f'<tr valign="bottom" style="height:{height_px}px;">{"".join(cells)}</tr></table>'
    )


_FOCUS_CHART_HEIGHT_PX = 56
_FOCUS_MAX_HEADLINES = 2
_FOCUS_COLUMN_PX = CONTENT_WIDTH_PX // 2


def render_news_charts_section(charts: list[NewsChart]) -> str:
    """Seccion "En foco": un grafico de 1 mes por activo mencionado en las noticias.

    Dos columnas en escritorio, una en telefonos. Cada tarjeta muestra
    precio, variacion del dia y del periodo, la lectura de Nix (rotulada como
    IA) y el o los titulares que activaron el grafico.
    """
    cards: list[str] = []
    for chart in charts:
        snap = chart.snapshot
        chart_html = _column_chart(
            snap.history, width="100%", height_px=_FOCUS_CHART_HEIGHT_PX, spacing=2, color=DMAC_INK
        )
        if not chart_html:
            continue
        change_text, change_color = format_snapshot_change(snap)
        period = chart.period_change_pct
        period_text = (
            ""
            if period is None
            else f" &middot; {len(snap.history)} cierres: {'+' if period >= 0 else ''}{format_number(period, 1)}%"
        )
        low, high = min(snap.history), max(snap.history)
        source = _SOURCE_LABELS.get(snap.source or "", snap.source or "-")
        headlines = "".join(_focus_headline(item) for item in chart.news[:_FOCUS_MAX_HEADLINES])
        # La lectura es interpretacion de la IA: va rotulada y separada de los datos.
        reading = (
            f"<div style=\"font-size: 13px; line-height: 1.45; color: {DMAC_TEXT}; margin-top: 8px;\">"
            f"<strong style=\"color: {DMAC_BRAND_PRIMARY};\">Lectura de Nix (IA):</strong>"
            f" <em>{escape(chart.reading)}</em></div>"
            if chart.reading
            else ""
        )
        cards.append(
            "<div class=\"dmac-col-pad\" style=\"padding: 0 24px 22px 0;\">"
            "<table role=\"presentation\" cellspacing=\"0\" cellpadding=\"0\" border=\"0\" width=\"100%\"><tr>"
            f"<td style=\"font-family: {DMAC_SERIF}; font-size: 17px; font-weight: 700; color: {DMAC_INK};\">"
            f"{escape(snap.name or snap.symbol)}</td>"
            f"<td align=\"right\" style=\"font-size: 13px; color: {DMAC_TEXT}; white-space: nowrap;\">"
            f"{format_snapshot_value(snap)} "
            f"<strong style=\"color: {change_color};\">{change_text}</strong></td>"
            "</tr></table>"
            f"<div style=\"margin-top: 6px; border-bottom: 1px solid {DMAC_INK};\">{chart_html}</div>"
            f"<div style=\"font-size: 12px; color: {DMAC_MUTED}; margin-top: 4px;\">"
            f"{escape(source)}{period_text} &middot; mín. {format_number(low)} / máx. {format_number(high)}</div>"
            f"{reading}"
            f"<div style=\"font-size: 12px; color: {DMAC_MUTED}; margin-top: 8px;\">Por la noticia:</div>"
            f"{headlines}"
            "</div>"
        )

    if not cards:
        return ""

    return _section_row(
        section_eyebrow("En foco · activos en las noticias", strong_rule=True)
        + f"<div style=\"margin: -4px 0 14px 0; font-size: 13px; color: {DMAC_MUTED};\">"
        "Gráficos elegidos según los titulares de hoy. Último mes de cierres diarios.</div>"
        + fluid_columns(cards, _FOCUS_COLUMN_PX, "dmac-col")
    )


def _focus_headline(item) -> str:
    url = _normalize_url(getattr(item, "url", "") or "")
    title = escape(item.title)
    source = escape(item.source or "")
    if url:
        title = (
            f"<a href=\"{escape(url)}\" target=\"_blank\" rel=\"noopener noreferrer\""
            f" style=\"color: {DMAC_BRAND_PRIMARY}; text-decoration: none;\">{title}</a>"
        )
    return (
        f"<div style=\"font-size: 13px; line-height: 1.4; margin-top: 3px;\">{title}"
        f" <span style=\"color: {DMAC_MUTED};\">({source})</span></div>"
    )


def _group_snapshots(snapshots: list[MarketSnapshot]) -> list[tuple[str, list[MarketSnapshot]]]:
    by_symbol = {snap.symbol: snap for snap in snapshots}
    grouped: list[tuple[str, list[MarketSnapshot]]] = []
    used: set[str] = set()
    for title, symbols in MARKET_GROUPS:
        members = [by_symbol[symbol] for symbol in symbols if symbol in by_symbol]
        used.update(symbol for symbol in symbols if symbol in by_symbol)
        if members:
            grouped.append((title, members))
    others = [snap for snap in snapshots if snap.symbol not in used]
    if others:
        grouped.append(("Otros", others))
    return grouped


def render_assets_table(snapshots: list[MarketSnapshot]) -> str:
    """Tabla de mercados agrupada (Chile, EE.UU., materias primas, resto).

    Columnas: activo, ultimo, variacion del dia y sparkline de 1 mes. La
    fuente va en la nota al pie ("Yahoo Finance salvo indicacion") y solo se
    repite bajo el nombre cuando es otra (BCCh). Cabe sin scroll horizontal
    desde ~320 px.
    """
    visible = [snap for snap in snapshots if not (snap.price is None and snap.change_pct is None)]
    if not visible:
        return _section_row(
            f"<p style=\"margin: 0; color: {DMAC_MUTED};\"><em>Mercado cerrado o sin datos disponibles al momento.</em></p>",
            top=16,
        )

    with_trend = any(len(snap.history) >= _SPARK_MIN_POINTS for snap in visible)
    cell = f"border-bottom: 1px solid {DMAC_RULE_SOFT}; padding: 7px 0;"
    rows: list[str] = []
    for title, members in _group_snapshots(visible):
        rows.append(
            f"<tr><td colspan=\"4\" style=\"padding: 14px 0 4px 0; font-size: 11px; font-weight: 700;"
            f" color: {DMAC_MUTED}; text-transform: uppercase; letter-spacing: 1px;\">{escape(title)}</td></tr>"
        )
        for snap in members:
            notes: list[str] = []
            if (snap.source or "") != _DEFAULT_TABLE_SOURCE:
                notes.append(_SOURCE_LABELS.get(snap.source or "", snap.source or "-"))
            as_of = format_as_of(snap)
            if as_of:
                # Ultimo dato valido (la fuente no trajo datos hoy): se rotula
                # con su fecha para no presentarlo como precio actual.
                notes.append(as_of)
            note_html = (
                f" <span style=\"font-weight: 400; font-size: 11px; color: {DMAC_MUTED};\">"
                f"{escape(' · '.join(notes))}</span>"
                if notes
                else ""
            )
            change_text, change_color = format_snapshot_change(snap)
            spark = (render_sparkline(snap.history) or "&nbsp;") if with_trend else ""
            rows.append(
                "<tr>"
                f"<td style=\"{cell} font-size: 14px; font-weight: 600; color: {DMAC_TEXT};\">"
                f"{escape(snap.name or snap.symbol)}{note_html}</td>"
                f"<td align=\"right\" style=\"{cell} padding-left: 8px; font-size: 14px; color: {DMAC_TEXT};"
                f" white-space: nowrap;\">{format_snapshot_value(snap)}</td>"
                f"<td align=\"right\" style=\"{cell} padding-left: 8px; font-size: 14px; font-weight: 700;"
                f" color: {change_color}; white-space: nowrap;\">{change_text}</td>"
                f"<td align=\"right\" style=\"{cell} padding-left: 10px; width: {_SPARK_WIDTH_PX}px;\">{spark}</td>"
                "</tr>"
            )

    header_style = (
        f"padding: 0 0 6px 0; font-size: 11px; color: {DMAC_MUTED}; font-weight: 700;"
        f" text-transform: uppercase; letter-spacing: 0.5px; border-bottom: 1px solid {DMAC_INK};"
    )
    header = (
        "<tr>"
        f"<td style=\"{header_style}\">Activo</td>"
        f"<td align=\"right\" style=\"{header_style}\">Último</td>"
        f"<td align=\"right\" style=\"{header_style}\">Día</td>"
        f"<td align=\"right\" style=\"{header_style}\">{'1 mes' if with_trend else '&nbsp;'}</td>"
        "</tr>"
    )
    footnote = (
        f"<div style=\"margin-top: 8px; font-size: 12px; color: {DMAC_MUTED};\">"
        "Fuente: Yahoo Finance salvo indicación (BCCh: Banco Central de Chile)."
        " Tasas en % y su variación en puntos base (pb)."
        f"{' 1 mes: cierres diarios.' if with_trend else ''}</div>"
    )
    return _section_row(
        section_eyebrow("Mercados", strong_rule=False)
        + "<table role=\"presentation\" cellspacing=\"0\" cellpadding=\"0\" border=\"0\" width=\"100%\""
        " style=\"border-collapse: collapse;\">"
        + header
        + "".join(rows)
        + "</table>"
        + footnote
    )
