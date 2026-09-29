"""HTML email formatter for the DMAC briefs (diseno "Editorial").

Renders text briefs (morning, market close, alerts) into an HTML email with
a newspaper-like look: masthead with the DMAC logo, serif headlines on an
ivory ground, thin rules between sections, grouped market table, "En foco"
charts and a footer disclaimer plus the Nix signature.

Compatibilidad de clientes (ver docs/email-output.md):
- Todo el layout es con tablas y estilos inline; `<style>` solo agrega la
  media query para telefonos.
- Responsivo sin depender de la media query: las grillas (cifras clave,
  "En foco") son bloques `inline-block` con ancho maximo que se apilan solos
  cuando no caben (clientes que ignoran `@media`, como algunas apps de
  Outlook). Outlook de escritorio (motor Word) no entiende `inline-block`: ahi
  las mismas columnas van en una tabla dentro de comentarios condicionales
  `<!--[if mso]>`.
- Colores en hex y `bgcolor` en las celdas con fondo (Outlook ignora
  `rgba()` y a veces `background`); sin degradados ni imagenes de fondo.
- Fuentes seguras: Georgia para titulares y Segoe UI/Helvetica/Arial para
  texto. Outlook no carga fuentes web.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from html import escape
from zoneinfo import ZoneInfo

from services.email_assets import get_logo_img_tag
from storage.models import MarketSnapshot

# Paleta editorial. Los nombres DMAC_* se mantienen porque otros modulos los
# importan. Tarjeta blanca pura y texto casi negro: los clientes con modo
# oscuro (Outlook nuevo/web, Gmail) invierten bien blanco/negro, pero el
# marfil del primer diseno quedaba cafe grisaceo. El correo no trae paleta
# oscura propia: Outlook nuevo la aplicaba segun el tema de Windows (aunque
# el lector eligiera "fondo claro") y encima convertia los colores.
DMAC_INK = "#16223a"
DMAC_PAPER = "#ffffff"
DMAC_PAGE = "#eef0f3"
DMAC_RULE = "#dcdfe5"
DMAC_RULE_SOFT = "#eaecf0"
DMAC_BODY_SOFT = "#374151"
DMAC_BRAND_PRIMARY = "#1e4f8c"
DMAC_BRAND_PRIMARY_DARK = DMAC_INK
DMAC_BG = "#f5f6f8"
DMAC_CARD = DMAC_PAPER
DMAC_TEXT = DMAC_INK
DMAC_MUTED = "#5b6475"
DMAC_BORDER = DMAC_RULE
DMAC_POSITIVE = "#1a7348"
DMAC_NEGATIVE = "#b42318"
DMAC_NEUTRAL = DMAC_MUTED
DMAC_LINK = DMAC_BRAND_PRIMARY
# Sin font-family explicito, Outlook de escritorio usa Times New Roman.
DMAC_FONT_FAMILY = "'Segoe UI', Helvetica, Arial, sans-serif"
DMAC_SERIF = "Georgia, 'Times New Roman', serif"

# Ancho maximo del correo y padding lateral de las secciones.
EMAIL_WIDTH_PX = 640
_SIDE_PX = 32
# Ancho util real: se resta el borde de 1 px del contenedor. Con 576 en vez
# de 574, tres columnas de 192 px no cabian y se apilaban en escritorio.
CONTENT_WIDTH_PX = EMAIL_WIDTH_PX - 2 - 2 * _SIDE_PX

# Media query para telefonos. Los clientes que la ignoran igual muestran el
# correo sin scroll horizontal: las columnas fluidas se apilan solas.
_MOBILE_STYLE = (
    "@media only screen and (max-width: 480px) {"
    " .dmac-outer { padding: 0 !important; }"
    " .dmac-px { padding-left: 16px !important; padding-right: 16px !important; }"
    " .dmac-mast { font-size: 32px !important; }"
    " .dmac-lead { font-size: 22px !important; }"
    " .dmac-kpi { max-width: 50% !important; }"
    " .dmac-col { max-width: 100% !important; }"
    " .dmac-col-pad { padding-right: 0 !important; }"
    "}"
)

_CHILE_TZ = ZoneInfo("America/Santiago")
_WEEKDAYS = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
_MONTHS = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)
_EDITION_LABELS = {
    "morning brief": "Edición de la mañana",
    "market close": "Edición de cierre",
    "alerta de alto impacto": "Alerta de alto impacto",
}


@dataclass(frozen=True)
class _Block:
    kind: str
    title: str
    bullets: list[str]
    table: str | None = None
    chart: str | None = None


_HEADING_RE = re.compile(r"^\s*(\d+)\.\s+(.+)$")
_BULLET_RE = re.compile(r"^\s*\*\s+(.+)$")
_SUBJECT_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_SUBJECT_TAG_RE = re.compile(r"^\s*\[([^\]]{1,20})\]")


def _render_blocks(text_body: str) -> list[_Block]:
    """Parse the brief text into structured blocks.

    Heuristic: a paragraph starting with "N. Title" starts a new section.
    Lines starting with "* " are bullets. Blank lines separate paragraphs.
    Plain lines (no heading, no bullet) become paragraph content inside the
    current section, or into a synthetic intro block if no section exists yet.
    """
    blocks: list[_Block] = []
    current: _Block | None = None
    paragraph_buffer: list[str] = []
    saw_heading = False

    def _flush_paragraph() -> None:
        nonlocal current
        if not paragraph_buffer:
            return
        if current is None:
            current = _Block(kind="intro", title="", bullets=[])
        joined = " ".join(paragraph_buffer).strip()
        if joined:
            current.bullets.append(joined)
        paragraph_buffer.clear()

    for raw_line in text_body.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            _flush_paragraph()
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            _flush_paragraph()
            if current and (current.bullets or current.title):
                blocks.append(current)
            current = _Block(kind="section", title=heading.group(2).strip(), bullets=[])
            saw_heading = True
            continue
        bullet = _BULLET_RE.match(line)
        if bullet:
            _flush_paragraph()
            if current is None:
                kind = "section" if saw_heading else "intro"
                current = _Block(kind=kind, title="", bullets=[])
            current.bullets.append(bullet.group(1).strip())
            continue
        paragraph_buffer.append(line.strip())

    _flush_paragraph()
    if current and (current.bullets or current.title):
        blocks.append(current)
    if not blocks and text_body.strip():
        blocks.append(_Block(kind="intro", title="", bullets=[text_body.strip()]))
    return blocks


def _normalize_url(url: str) -> str:
    """Return a safe absolute URL or '' for invalid/empty input."""
    if not url:
        return ""
    cleaned = url.strip()
    if not (cleaned.startswith("http://") or cleaned.startswith("https://")):
        return ""
    return cleaned


# --- Numeros (formato chileno: 1.234,56) ---------------------------------


def format_number(value: float, decimals: int = 2) -> str:
    """Numero con separador de miles "." y decimal "," (formato chileno)."""
    text = f"{value:,.{decimals}f}"
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _format_price(value: float | None) -> str:
    if value is None:
        return "-"
    return format_number(value, 2)


def _format_change(value: float | None) -> str:
    if value is None:
        return "s/d"
    return f"{format_number(value, 2) if value < 0 else '+' + format_number(value, 2)}%"


def _color_for_change(value: float | None) -> str:
    if value is None:
        return DMAC_NEUTRAL
    if value > 0:
        return DMAC_POSITIVE
    if value < 0:
        return DMAC_NEGATIVE
    return DMAC_NEUTRAL


# --- Piezas de layout -------------------------------------------------------


def _section_row(inner: str, top: int = 28) -> str:
    return (
        f"<tr><td class=\"dmac-px\" style=\"padding: {top}px {_SIDE_PX}px 0 {_SIDE_PX}px;\">"
        f"{inner}</td></tr>"
    )


def section_eyebrow(title: str, strong_rule: bool = False) -> str:
    """Rotulo de seccion: mayusculas pequenas en azul sobre una linea fina."""
    rule = DMAC_INK if strong_rule else DMAC_RULE
    return (
        f"<div style=\"font-size: 12px; letter-spacing: 1.5px; text-transform: uppercase;"
        f" color: {DMAC_BRAND_PRIMARY}; font-weight: 700; padding-bottom: 6px;"
        f" border-bottom: 1px solid {rule}; margin: 0 0 12px 0;\">{escape(title)}</div>"
    )


def fluid_columns(cells: list[str], column_px: int, css_class: str) -> str:
    """Columnas que se apilan solas en pantallas angostas.

    Cada celda es un bloque `inline-block` de ancho maximo `column_px`; si no
    caben lado a lado, bajan a la linea siguiente (sin media query). Para
    Outlook de escritorio, que no respeta `inline-block`, las mismas celdas
    van en una tabla dentro de comentarios condicionales.
    """
    if not cells:
        return ""
    mso_open = (
        "<!--[if mso]><table role=\"presentation\" cellspacing=\"0\" cellpadding=\"0\""
        " border=\"0\" width=\"100%\"><tr><![endif]-->"
    )
    parts = [mso_open, "<div style=\"font-size: 0; line-height: 0; text-align: left;\">"]
    for cell in cells:
        parts.append(
            f"<!--[if mso]><td width=\"{column_px}\" valign=\"top\"><![endif]-->"
            f"<div class=\"{css_class}\" style=\"display: inline-block; vertical-align: top;"
            f" width: 100%; max-width: {column_px}px; font-size: 14px; line-height: 1.45;\">"
            f"{cell}</div>"
            "<!--[if mso]></td><![endif]-->"
        )
    parts.append("</div><!--[if mso]></tr></table><![endif]-->")
    return "".join(parts)


def _link(url: str, label_html: str, color: str = DMAC_LINK, extra_style: str = "") -> str:
    return (
        f"<a href=\"{escape(url)}\" target=\"_blank\" rel=\"noopener noreferrer\""
        f" style=\"color: {color}; text-decoration: none;{extra_style}\">{label_html}</a>"
    )


# --- Secciones --------------------------------------------------------------


def _bullet_with_link(label: str, url: str) -> str:
    safe_label = escape(label)
    if url:
        return f'<li style="margin: 0 0 6px 0; line-height: 1.5;">{_link(url, safe_label)}</li>'
    return f'<li style="margin: 0 0 6px 0; line-height: 1.5;">{safe_label}</li>'


def _render_section_html(block: _Block, links: dict[str, str] | None = None) -> str:
    links = links or {}
    if block.kind == "intro":
        body = "".join(
            f"<p style=\"margin: 0 0 8px 0; font-size: 15px; line-height: 1.55;\">{escape(line)}</p>"
            for line in block.bullets
        )
        return _section_row(body, top=24)

    title_html = section_eyebrow(block.title) if block.title else ""
    list_items = "".join(_bullet_with_link(bullet, links.get(bullet, "")) for bullet in block.bullets)
    body_html = (
        f"<ul style=\"margin: 0; padding-left: 18px; color: {DMAC_TEXT}; font-size: 15px;\">{list_items}</ul>"
        if list_items
        else ""
    )
    return _section_row(f"{title_html}{body_html}")


def render_assets_table(snapshots: list[MarketSnapshot]) -> str:
    """Backwards-compatible wrapper: delegates to services.email_charts."""
    from services.email_charts import render_assets_table as _impl

    return _impl(snapshots)


def render_news_list(
    title: str,
    news_items: Iterable,
    logo_path: str = "",
) -> str:
    """Titulares con link a la fuente: titulo en serif y "Fuente · Region"."""
    items = list(news_items)
    if not items:
        return ""
    rows: list[str] = []
    for item in items[:8]:
        url = _normalize_url(getattr(item, "url", "") or "")
        title_text = escape(item.title)
        title_html = (
            _link(url, title_text, color=DMAC_INK)
            if url
            else title_text
        )
        meta = f"{escape(item.source)} &middot; {escape(item.region or 'Global')}"
        rows.append(
            f"<div style=\"padding: 0 0 12px 0; margin: 0 0 12px 0; border-bottom: 1px solid {DMAC_RULE_SOFT};\">"
            f"<div style=\"font-family: {DMAC_SERIF}; font-size: 17px; line-height: 1.35;"
            f" font-weight: 700; color: {DMAC_INK};\">{title_html}</div>"
            f"<div style=\"font-size: 13px; color: {DMAC_MUTED}; margin-top: 4px;\">{meta}</div>"
            "</div>"
        )
    return _section_row(section_eyebrow(title) + "".join(rows))


def render_chart_section(chart_id: str, chart_html: str) -> str:
    """Wrap a chart fragment for the email."""
    return _section_row(f"<div style=\"border: 1px solid {DMAC_RULE}; padding: 12px;\">{chart_html}</div>")


def render_market_sentiment_section(sentiment) -> str:
    """Sentimiento de mercado en una linea: etiqueta, puntaje y resumen."""
    if sentiment is None:
        return ""
    score = max(0, min(100, int(getattr(sentiment, "score", 50))))
    label = str(getattr(sentiment, "label", "Neutral"))
    summary = str(getattr(sentiment, "summary", ""))
    source = str(getattr(sentiment, "source", ""))
    color = _sentiment_color(score)
    source_html = f" Fuente: {escape(source)}." if source else ""
    return _section_row(
        f"<div style=\"border-top: 1px solid {DMAC_RULE}; border-bottom: 1px solid {DMAC_RULE}; padding: 10px 0;\">"
        f"<div style=\"font-size: 12px; letter-spacing: 1.5px; text-transform: uppercase; color: {DMAC_MUTED};"
        " font-weight: 700;\">Sentimiento de mercado</div>"
        f"<div style=\"margin-top: 4px; font-size: 15px; color: {DMAC_TEXT};\">"
        f"<strong style=\"color: {color};\">{escape(label)}</strong> &middot; {score}/100</div>"
        f"<div style=\"margin-top: 4px; font-size: 13px; line-height: 1.5; color: {DMAC_BODY_SOFT};\">"
        f"{escape(summary)}<span style=\"color: {DMAC_MUTED};\">{source_html}</span></div>"
        "</div>",
        top=20,
    )


def _sentiment_color(score: int) -> str:
    if score >= 56:
        return DMAC_POSITIVE
    if score <= 44:
        return DMAC_NEGATIVE
    return DMAC_NEUTRAL


def render_unavailable_sources(sources: list[str]) -> str:
    """Linea discreta con las fuentes que no trajeron datos en esta edicion."""
    names = ", ".join(escape(source) for source in dict.fromkeys(sources))
    return _section_row(
        f"<p style=\"margin: 0; font-size: 13px; color: {DMAC_MUTED};\">"
        f"Sin datos en esta edición: {names}.</p>",
        top=16,
    )


# --- Cifras clave ------------------------------------------------------------

# Cifras destacadas bajo "Lo esencial", en este orden, si hay dato.
KEY_FIGURE_SYMBOLS: tuple[str, ...] = ("USDCLP", "COPPER", "IPSA", "TPM")


def render_key_figures(snapshots: list[MarketSnapshot]) -> str:
    """Franja de 4 cifras clave (2x2 en telefonos)."""
    from services.email_charts import format_snapshot_change, format_snapshot_value

    by_symbol = {snap.symbol: snap for snap in snapshots if snap.price is not None}
    selected = [by_symbol[symbol] for symbol in KEY_FIGURE_SYMBOLS if symbol in by_symbol]
    if not selected:
        return ""
    column_px = CONTENT_WIDTH_PX // len(selected)
    cells = []
    for snap in selected:
        change_text, change_color = format_snapshot_change(snap)
        cells.append(
            f"<div style=\"padding: 10px 10px 10px 0;\">"
            f"<div style=\"font-size: 12px; text-transform: uppercase; letter-spacing: 1px; color: {DMAC_MUTED};\">"
            f"{escape(snap.name or snap.symbol)}</div>"
            f"<div style=\"font-family: {DMAC_SERIF}; font-size: 22px; font-weight: 700; color: {DMAC_INK};\">"
            f"{format_snapshot_value(snap)}</div>"
            f"<div style=\"font-size: 13px; font-weight: 700; color: {change_color};\">{change_text}</div>"
            "</div>"
        )
    return _section_row(
        f"<div style=\"border-top: 1px solid {DMAC_INK};\">{fluid_columns(cells, column_px, 'dmac-kpi')}</div>",
        top=22,
    )


# --- Analisis de Nix -------------------------------------------------------

_NIX_SKIPPED_SECTIONS = {"visualizaciones", "a vigilar", "fuentes", "cautelas editoriales"}


def render_nix_editorial(email) -> str:
    """HTML del analisis de Nix (AiEditorialEmail) con el estilo editorial.

    Titular, resumen numerado, una seccion por region (Chile primero), "A
    vigilar" y cautelas. Las viñetas de cada seccion solo se muestran si la
    seccion no trae parrafos: suelen repetir el titular en ingles.
    """
    parts: list[str] = []
    headline = str(getattr(email, "headline", "") or "").strip()
    if headline:
        parts.append(
            f"<div class=\"dmac-lead\" style=\"font-family: {DMAC_SERIF}; font-size: 25px; line-height: 1.25;"
            f" font-weight: 700; color: {DMAC_INK}; margin: 0 0 14px 0;\">{escape(headline)}</div>"
        )
    summary = list(getattr(email, "executive_summary", []) or [])[:4]
    if summary:
        rows = "".join(
            "<tr>"
            f"<td valign=\"top\" style=\"width: 22px; padding: 0 0 10px 0; font-family: {DMAC_SERIF};"
            f" font-size: 15px; font-weight: 700; color: {DMAC_BRAND_PRIMARY};\">{index}</td>"
            f"<td valign=\"top\" style=\"padding: 0 0 10px 0; font-size: 15px; line-height: 1.5; color: {DMAC_TEXT};\">"
            f"{escape(point)}</td></tr>"
            for index, point in enumerate(summary, start=1)
        )
        parts.append(
            "<table role=\"presentation\" cellspacing=\"0\" cellpadding=\"0\" border=\"0\" width=\"100%\">"
            f"{rows}</table>"
        )

    sections = [
        section
        for section in getattr(email, "sections", []) or []
        if section.heading and section.heading.strip().lower() not in _NIX_SKIPPED_SECTIONS
    ]
    sections.sort(key=lambda section: 0 if section.heading.strip().lower() == "chile" else 1)
    for section in sections:
        paragraphs = "".join(
            f"<p style=\"margin: 0 0 10px 0; font-size: 15px; line-height: 1.55;"
            f" color: {DMAC_TEXT if index == 0 else DMAC_BODY_SOFT};\">{escape(line)}</p>"
            for index, line in enumerate(section.body)
        )
        bullets = ""
        if not section.body and section.bullets:
            items = "".join(f"<li style=\"margin: 0 0 4px 0;\">{escape(b)}</li>" for b in section.bullets[:4])
            bullets = f"<ul style=\"margin: 0 0 10px 0; padding-left: 18px; font-size: 14px;\">{items}</ul>"
        parts.append(
            f"<div style=\"margin: 18px 0 0 0;\">{section_eyebrow(section.heading)}{paragraphs}{bullets}</div>"
        )

    risk_flags = list(getattr(email, "risk_flags", []) or [])[:5]
    if risk_flags:
        items = "".join(f"<li style=\"margin: 0 0 4px 0;\">{escape(flag)}</li>" for flag in risk_flags)
        parts.append(
            f"<div style=\"margin: 18px 0 0 0;\">{section_eyebrow('A vigilar')}"
            f"<ul style=\"margin: 0; padding-left: 18px; font-size: 14px; line-height: 1.5;"
            f" color: {DMAC_TEXT};\">{items}</ul></div>"
        )
    cautions = list(getattr(email, "editorial_cautions", []) or [])[:3]
    if cautions:
        text = " ".join(escape(caution) for caution in cautions)
        parts.append(
            f"<p style=\"margin: 14px 0 0 0; font-size: 13px; line-height: 1.5; color: {DMAC_MUTED};\">"
            f"<strong>Cautela:</strong> {text}</p>"
        )
    return "".join(parts)


def _nix_analysis_section(
    html: str,
    nix_chart_pngs: dict[str, bytes] | None = None,
) -> str:
    """Bloque "Lo esencial": el analisis de Nix, rotulado como IA.

    `html` se inserta tal cual (quien llama lo sanitiza; ver
    `render_nix_editorial`). `nix_chart_pngs` se acepta por compatibilidad y se
    ignora: en el MVP los graficos IA no van en el correo (ver AGENTS.md).
    """
    del nix_chart_pngs  # intentionally unused in MVP
    content = html if html.strip() else (
        f"<p style=\"margin: 0; color: {DMAC_MUTED};\"><em>Análisis de Nix no disponible para esta edición.</em></p>"
    )
    return _section_row(
        section_eyebrow("Lo esencial · Análisis de Nix (IA)")
        + content
        + f"<p style=\"margin: 12px 0 0 0; font-size: 13px; color: {DMAC_MUTED};\">"
        "Redactado por Nix a partir de titulares públicos y precios de mercado."
        " Interpretación preliminar.</p>",
        top=26,
    )


# --- Vista previa en la bandeja --------------------------------------------

_LEAD_RE = re.compile(r'class="dmac-lead"[^>]*>([^<]+)<')
_PREHEADER_MAX = 140
# Relleno invisible: sin el, Gmail/Outlook completan la vista previa con el
# texto que sigue (la cabecera "PRUEBA · DATA MARKET ANALYSIS CLUB UDD").
_PREHEADER_FILLER = "&#847;&zwnj;&nbsp;" * 60


def extract_nix_headline(nix_html: str | None) -> str:
    """Titular de Nix (texto plano) desde el HTML de `render_nix_editorial`."""
    from html import unescape

    lead = _LEAD_RE.search(nix_html or "")
    return " ".join(unescape(lead.group(1)).split()) if lead else ""


def _default_preheader(nix_html: str | None, news_items: list | None, intro: str) -> str:
    """Titular de Nix, o el primer titular de noticias, o la intro."""
    lead = _LEAD_RE.search(nix_html or "")
    if lead:
        return lead.group(1).strip()
    for item in news_items or []:
        title = str(getattr(item, "title", "") or "").strip()
        if title:
            return title
    return intro


def render_preheader(text: str) -> str:
    """Texto oculto que la bandeja muestra como vista previa del correo."""
    from html import unescape

    clean = " ".join(unescape(text).split())
    if len(clean) > _PREHEADER_MAX:
        clean = clean[: _PREHEADER_MAX - 1].rstrip() + "…"
    return (
        "<div style=\"display: none; max-height: 0; overflow: hidden; mso-hide: all; font-size: 1px;"
        f" line-height: 1px; color: {DMAC_PAGE}; opacity: 0;\">{escape(clean)}{_PREHEADER_FILLER}</div>"
    )


# --- Cabecera y pie ---------------------------------------------------------


def edition_label(brief_kind: str) -> str:
    return _EDITION_LABELS.get(brief_kind.strip().lower(), brief_kind.strip().capitalize() or "Brief")


def long_spanish_date(subject: str, now: datetime | None = None, edition_date: date | None = None) -> str:
    """"Martes 29 de septiembre de 2026": fecha de la edicion, la del asunto o hoy en Chile."""
    match = _SUBJECT_DATE_RE.search(subject)
    try:
        day = datetime(int(match.group(1)), int(match.group(2)), int(match.group(3))) if match else None
    except ValueError:
        day = None
    if edition_date is not None:
        day = datetime(edition_date.year, edition_date.month, edition_date.day)
    if day is None:
        day = (now or datetime.now(_CHILE_TZ)).astimezone(_CHILE_TZ)
    weekday = _WEEKDAYS[day.weekday()].capitalize()
    return f"{weekday} {day.day} de {_MONTHS[day.month - 1]} de {day.year}"


def _header_html(
    subject: str,
    intro: str,
    logo_path: str = "",
    logo_url: str = "",
    brief_kind: str = "brief",
    edition_date: date | None = None,
) -> str:
    logo_img = get_logo_img_tag(logo_path, width=56, url=logo_url)
    # Con el logo embebido (cid:), el fondo blanco viene dentro del PNG: el
    # modo oscuro de los clientes no puede oscurecerlo (no invierte imagenes).
    logo_cell = f"<td valign=\"middle\" style=\"padding: 0 14px 0 0;\">{logo_img}</td>" if logo_img else ""
    tag_match = _SUBJECT_TAG_RE.match(subject)
    tag_html = (
        f"<span style=\"color: {DMAC_NEGATIVE}; font-weight: 700;\">{escape(tag_match.group(1))}</span> &middot; "
        if tag_match
        else ""
    )
    small = f"font-size: 12px; letter-spacing: 1.5px; text-transform: uppercase; color: {DMAC_MUTED};"
    intro_html = (
        f"<p style=\"margin: 14px 0 0 0; font-size: 14px; line-height: 1.5; color: {DMAC_BODY_SOFT};\">"
        f"{escape(intro)}</p>"
        if intro
        else ""
    )
    return (
        f"<tr><td class=\"dmac-px\" style=\"padding: 26px {_SIDE_PX}px 18px {_SIDE_PX}px;"
        f" border-bottom: 3px double {DMAC_INK};\">"
        "<table role=\"presentation\" cellspacing=\"0\" cellpadding=\"0\" border=\"0\" width=\"100%\"><tr>"
        f"<td style=\"{small}\">{tag_html}Data Market Analysis Club UDD</td>"
        f"<td align=\"right\" style=\"{small}\">Coyuntura financiera</td>"
        "</tr></table>"
        "<table role=\"presentation\" cellspacing=\"0\" cellpadding=\"0\" border=\"0\" style=\"margin: 14px 0;\"><tr>"
        f"{logo_cell}"
        f"<td valign=\"middle\" class=\"dmac-mast\" style=\"font-family: {DMAC_SERIF}; font-size: 42px;"
        f" line-height: 1.1; font-weight: 700; color: {DMAC_INK};\">DMAC Brief</td>"
        "</tr></table>"
        "<table role=\"presentation\" cellspacing=\"0\" cellpadding=\"0\" border=\"0\" width=\"100%\"><tr>"
        f"<td style=\"border-top: 1px solid {DMAC_INK}; padding-top: 8px; font-size: 13px; color: {DMAC_INK};\">"
        f"{escape(long_spanish_date(subject, edition_date=edition_date))}</td>"
        f"<td align=\"right\" style=\"border-top: 1px solid {DMAC_INK}; padding-top: 8px; font-size: 13px;"
        f" color: {DMAC_INK};\">{escape(edition_label(brief_kind))}</td>"
        "</tr></table>"
        f"{intro_html}"
        "</td></tr>"
    )


def _footer_html() -> str:
    year = datetime.now(_CHILE_TZ).year
    return (
        f"<tr><td class=\"dmac-px\" style=\"padding: 20px {_SIDE_PX}px 26px {_SIDE_PX}px;"
        f" border-top: 3px double {DMAC_INK};\">"
        f"<p style=\"margin: 0; font-size: 13px; color: {DMAC_MUTED}; line-height: 1.55;\">"
        "Reporte generado automáticamente por <strong>DMAC Market Brief Agent</strong>."
        " Los hechos se basan en titulares públicos y precios de mercado al momento del envío."
        " Las interpretaciones son preliminares y no constituyen recomendación de inversión.</p>"
        f"<p style=\"margin: 10px 0 0 0; font-size: 13px; color: {DMAC_MUTED}; line-height: 1.5;\">"
        f"<strong style=\"color: {DMAC_TEXT};\">Nix Assistant, DMAC UDD</strong> &middot; Equipo de Datos y Coyuntura"
        f" &middot; &copy; {year} Data Market Analysis Club UDD</p>"
        "</td></tr>"
    )


def _build_intro_paragraph(intro_lines: list[str], brief_kind: str) -> str:
    """Build the friendly intro line: 'Equipo, les comparto el ...'."""
    raw = " ".join(line for line in intro_lines if line).strip()
    if not raw:
        return f"Equipo, les comparto el {brief_kind} de hoy."
    if "Equipo" in raw or "les comparto" in raw.lower():
        return raw
    return f"Equipo, les comparto el {brief_kind} de hoy.\n{raw}"


def build_email_html(
    subject: str,
    text_body: str,
    snapshots: list[MarketSnapshot] | None = None,
    news_items: list | None = None,
    news_title: str = "Titulares principales",
    brief_kind: str = "brief",
    news_link_map: dict[str, str] | None = None,
    logo_path: str = "",
    logo_url: str = "",
    include_charts: bool = True,
    nix_analysis_html: str | None = None,
    nix_chart_pngs: dict[str, bytes] | None = None,
    include_deterministic_brief: bool = True,
    market_sentiment=None,
    max_news_charts: int = 3,
    news_charts: list | None = None,
    unavailable_sources: list[str] | None = None,
    preheader: str | None = None,
    edition_date: date | None = None,
) -> str:
    """Build the HTML email from text body, snapshots, news and AI analysis.

    Orden: cabecera, "Lo esencial" (Nix), cifras clave, secciones
    deterministicas (si no hay IA), sentimiento, titulares, mercados, "En
    foco", fuentes sin datos y pie. Los graficos son HTML/CSS estatico (sin
    JavaScript ni imagenes). `news_charts` permite pasar los graficos "En
    foco" ya elegidos (con lecturas de Nix); si se omite se eligen aqui.
    """
    from services.email_charts import (
        render_assets_table as _render_assets_table,
    )
    from services.email_charts import (
        render_news_charts_section as _render_news_charts_section,
    )
    from services.news_charts import select_news_charts

    blocks = _render_blocks(text_body)
    intro_lines: list[str] = []
    body_blocks: list[_Block] = []
    for block in blocks:
        if block.kind == "intro":
            intro_lines.extend(block.bullets)
        else:
            body_blocks.append(block)
    intro_text = _build_intro_paragraph(intro_lines, brief_kind)

    section_rows: list[str] = []

    if nix_analysis_html:
        section_rows.append(_nix_analysis_section(nix_analysis_html, nix_chart_pngs))

    if include_charts and snapshots:
        section_rows.append(render_key_figures(snapshots))

    if include_deterministic_brief:
        section_rows.extend(_render_section_html(block, links=news_link_map or {}) for block in body_blocks)

    sentiment_html = render_market_sentiment_section(market_sentiment)
    if sentiment_html:
        section_rows.append(sentiment_html)

    if news_items:
        news_html = render_news_list(news_title, news_items, logo_path=logo_path)
        if news_html:
            section_rows.append(news_html)

    if include_charts and snapshots:
        section_rows.append(_render_assets_table(snapshots))
        # Graficos elegidos por los titulares (ver services/news_charts.py).
        if news_items:
            if news_charts is None:
                news_charts = select_news_charts(news_items, snapshots, max_charts=max_news_charts)
            focus_html = _render_news_charts_section(news_charts)
            if focus_html:
                section_rows.append(focus_html)

    if unavailable_sources:
        section_rows.append(render_unavailable_sources(unavailable_sources))

    body_html = "".join(section_rows) or _section_row(
        f"<p style=\"margin: 0; color: {DMAC_MUTED};\">Sin contenido relevante para esta corrida.</p>"
    )

    header_html = _header_html(
        subject, intro_text, logo_path=logo_path, logo_url=logo_url, brief_kind=brief_kind,
        edition_date=edition_date,
    )
    return (
        "<!doctype html><html lang=\"es\"><head>"
        "<meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"
        # Solo claro: los clientes con modo oscuro invierten el diseno por su
        # cuenta (ver la paleta arriba).
        "<meta name=\"color-scheme\" content=\"light\">"
        "<meta name=\"supported-color-schemes\" content=\"light\">"
        f"<title>{escape(subject)}</title>"
        f"<style>body, table, td, p, a, li, div {{ font-family: {DMAC_FONT_FAMILY}; }} {_MOBILE_STYLE}</style>"
        "</head>"
        f"<body bgcolor=\"{DMAC_PAGE}\" style=\"margin: 0; padding: 0; background: {DMAC_PAGE};"
        f" font-family: {DMAC_FONT_FAMILY}; color: {DMAC_TEXT};\">"
        f"{render_preheader(preheader or _default_preheader(nix_analysis_html, news_items, intro_text))}"
        "<table role=\"presentation\" cellspacing=\"0\" cellpadding=\"0\" border=\"0\" width=\"100%\""
        f" bgcolor=\"{DMAC_PAGE}\" style=\"width: 100%; background: {DMAC_PAGE};\">"
        "<tr><td align=\"center\" class=\"dmac-outer\" style=\"padding: 20px 12px;\">"
        f"<!--[if mso]><table role=\"presentation\" width=\"{EMAIL_WIDTH_PX}\" cellspacing=\"0\""
        " cellpadding=\"0\" border=\"0\"><tr><td><![endif]-->"
        "<table role=\"presentation\" cellspacing=\"0\" cellpadding=\"0\" border=\"0\" width=\"100%\""
        f" bgcolor=\"{DMAC_PAPER}\" style=\"width: 100%; max-width: {EMAIL_WIDTH_PX}px; background: {DMAC_PAPER};"
        f" border: 1px solid {DMAC_RULE}; color: {DMAC_TEXT};\">"
        f"{header_html}"
        f"{body_html}"
        "<tr><td style=\"height: 32px; line-height: 32px; font-size: 0;\">&nbsp;</td></tr>"
        f"{_footer_html()}"
        "</table>"
        "<!--[if mso]></td></tr></table><![endif]-->"
        "</td></tr></table></body></html>"
    )


def text_to_html(text_body: str) -> str:
    """Convert plain text to a simple, styled HTML preview (no assets/charts)."""
    return build_email_html(
        subject="DMAC Brief",
        text_body=text_body,
    )
