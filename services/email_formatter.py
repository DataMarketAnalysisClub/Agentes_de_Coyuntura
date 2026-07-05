"""Professional HTML email formatter for the DMAC briefs.

Renders text briefs (morning, market close, alerts) into a styled HTML email
with DMAC branding (inline logo), colored sections, proper bullet rendering,
market tables, optional embedded charts, clickable news links, and a footer
disclaimer plus the DMAC Nix team signature.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from html import escape

from services.email_assets import get_logo_img_tag
from storage.models import MarketSnapshot

DMAC_BRAND_PRIMARY = "#1d4ed8"
DMAC_BRAND_PRIMARY_DARK = "#1e3a8a"
DMAC_BRAND_ACCENT = "#0891b2"
DMAC_BG = "#f9fafb"
DMAC_CARD = "#ffffff"
DMAC_TEXT = "#111827"
DMAC_MUTED = "#6b7280"
DMAC_BORDER = "#e5e7eb"
DMAC_POSITIVE = "#16a34a"
DMAC_NEGATIVE = "#dc2626"
DMAC_NEUTRAL = "#6b7280"
DMAC_LINK = "#1d4ed8"


@dataclass(frozen=True)
class _Block:
    kind: str
    title: str
    bullets: list[str]
    table: str | None = None
    chart: str | None = None


_HEADING_RE = re.compile(r"^\s*(\d+)\.\s+(.+)$")
_BULLET_RE = re.compile(r"^\s*\*\s+(.+)$")


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


def _bullet_with_link(label: str, url: str) -> str:
    safe_label = escape(label)
    if url:
        return (
            f'<li style="margin: 0 0 6px 0; line-height: 1.5;">'
            f'<a href="{escape(url)}" style="color: {DMAC_LINK}; text-decoration: none;" '
            f'target="_blank" rel="noopener noreferrer">{safe_label}</a></li>'
        )
    return f'<li style="margin: 0 0 6px 0; line-height: 1.5;">{safe_label}</li>'


def _render_section_html(block: _Block, links: dict[str, str] | None = None) -> str:
    links = links or {}
    if block.kind == "intro":
        body = " ".join(
            f"<p style=\"margin: 0 0 8px 0; line-height: 1.55;\">{escape(line)}</p>"
            for line in block.bullets
        )
        return f"<tr><td style=\"padding: 20px 24px 0 24px;\">{body}</td></tr>"

    if block.title:
        title_html = (
            f"<h2 style=\"margin: 0 0 12px 0; font-size: 15px; color: {DMAC_BRAND_PRIMARY_DARK};"
            " letter-spacing: 0.02em; text-transform: uppercase;\">"
            f"{escape(block.title)}</h2>"
        )
    else:
        title_html = ""

    list_items = "".join(
        _bullet_with_link(bullet, links.get(bullet, ""))
        for bullet in block.bullets
    )
    if list_items:
        body_html = (
            f"<ul style=\"margin: 0; padding-left: 18px; color: {DMAC_TEXT};\">{list_items}</ul>"
        )
    else:
        body_html = ""

    return (
        "<tr><td style=\"padding: 20px 24px 0 24px;\">"
        f"{title_html}{body_html}"
        "</td></tr>"
    )


def _format_price(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:,.2f}"


def _format_change(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:+.2f}%"


def _color_for_change(value: float | None) -> str:
    if value is None:
        return DMAC_NEUTRAL
    if value > 0:
        return DMAC_POSITIVE
    if value < 0:
        return DMAC_NEGATIVE
    return DMAC_NEUTRAL


def render_assets_table(snapshots: list[MarketSnapshot]) -> str:
    """Backwards-compatible wrapper: delegates to services.email_charts."""
    from services.email_charts import render_assets_table as _impl
    return _impl(snapshots)


def render_news_list(
    title: str,
    news_items: Iterable,
    logo_path: str = "",
) -> str:
    """Render a styled list of news items, each title linked to its source URL."""
    items = list(news_items)
    if not items:
        return ""
    rows: list[str] = []
    for item in items[:8]:
        url = _normalize_url(getattr(item, "url", "") or "")
        title_html = (
            f"<a href=\"{escape(url)}\" target=\"_blank\" rel=\"noopener noreferrer\""
            f" style=\"color: {DMAC_LINK}; text-decoration: none; font-weight: 600;\">"
            f"{escape(item.title)}</a>"
            if url
            else f"<div style=\"font-weight: 600; color: {DMAC_TEXT};\">{escape(item.title)}</div>"
        )
        meta = (
            f"{escape(item.source)} &middot; {escape(item.region or 'Global')}"
        )
        if url:
            meta = (
                f"<a href=\"{escape(url)}\" target=\"_blank\" rel=\"noopener noreferrer\""
                f" style=\"color: {DMAC_MUTED}; text-decoration: none;\">{meta}</a>"
            )
        rows.append(
            "<tr>"
            f"<td style=\"padding: 10px 12px; border-bottom: 1px solid {DMAC_BORDER};\">"
            f"{title_html}"
            f"<div style=\"font-size: 11px; color: {DMAC_MUTED}; margin-top: 2px;\">"
            f"{meta}</div></td>"
            "</tr>"
        )
    return (
        "<tr><td style=\"padding: 20px 24px 0 24px;\">"
        f"<h2 style=\"margin: 0 0 12px 0; font-size: 15px; color: {DMAC_BRAND_PRIMARY_DARK};"
        " letter-spacing: 0.02em; text-transform: uppercase;\">"
        f"{escape(title)}</h2>"
        "<table role=\"presentation\" cellspacing=\"0\" cellpadding=\"0\" border=\"0\""
        f" style=\"width: 100%; border-collapse: collapse; background: {DMAC_CARD};"
        f" border: 1px solid {DMAC_BORDER}; border-radius: 6px; overflow: hidden;\">"
        f"{''.join(rows)}"
        "</table></td></tr>"
    )


def render_chart_section(chart_id: str, chart_html: str) -> str:
    """Wrap a Plotly chart fragment in a styled card for the email."""
    return (
        "<tr><td style=\"padding: 20px 24px 0 24px;\">"
        "<table role=\"presentation\" cellspacing=\"0\" cellpadding=\"0\" border=\"0\""
        f" style=\"width: 100%; background: {DMAC_CARD}; border: 1px solid {DMAC_BORDER};"
        " border-radius: 6px; overflow: hidden;\">"
        f"<tr><td style=\"padding: 12px;\">{chart_html}</td></tr>"
        "</table></td></tr>"
    )


def render_market_sentiment_section(sentiment) -> str:
    if sentiment is None:
        return ""
    score = max(0, min(100, int(getattr(sentiment, "score", 50))))
    label = str(getattr(sentiment, "label", "Neutral"))
    summary = str(getattr(sentiment, "summary", ""))
    source = str(getattr(sentiment, "source", ""))
    drivers = list(getattr(sentiment, "drivers", []) or [])[:4]
    color = _sentiment_color(score)
    driver_html = "".join(
        f"<li style=\"margin: 0 0 4px 0;\">{escape(str(driver))}</li>"
        for driver in drivers
    )
    if not driver_html:
        driver_html = "<li style=\"margin: 0 0 4px 0;\">Sin drivers dominantes.</li>"

    return (
        "<tr><td style=\"padding: 20px 24px 0 24px;\">"
        f"<h2 style=\"margin: 0 0 12px 0; font-size: 15px; color: {DMAC_BRAND_PRIMARY_DARK};"
        " letter-spacing: 0.02em; text-transform: uppercase;\">Sentimiento de mercado</h2>"
        f"<div style=\"background: {DMAC_CARD}; border: 1px solid {DMAC_BORDER};"
        " border-radius: 8px; padding: 14px 14px 12px 14px;\">"
        f"<div style=\"display: flex; align-items: baseline; justify-content: space-between; gap: 12px;\">"
        f"<div style=\"font-size: 18px; font-weight: 700; color: {color};\">{escape(label)}</div>"
        f"<div style=\"font-size: 13px; font-weight: 700; color: {DMAC_TEXT};\">{score}/100</div>"
        "</div>"
        f"<div style=\"margin: 10px 0 8px 0; height: 10px; background: {DMAC_BG};"
        " border-radius: 999px; overflow: hidden;\">"
        f"<div style=\"width: {score}%; height: 10px; background: {color}; border-radius: 999px;\"></div>"
        "</div>"
        f"<p style=\"margin: 0 0 8px 0; color: {DMAC_TEXT}; font-size: 13px; line-height: 1.45;\">"
        f"{escape(summary)}</p>"
        f"<ul style=\"margin: 0; padding-left: 18px; color: {DMAC_TEXT}; font-size: 12px; line-height: 1.45;\">"
        f"{driver_html}</ul>"
        f"<div style=\"margin-top: 8px; font-size: 11px; color: {DMAC_MUTED};\">Fuente: {escape(source)}</div>"
        "</div></td></tr>"
    )


def _sentiment_color(score: int) -> str:
    if score >= 56:
        return DMAC_POSITIVE
    if score <= 44:
        return DMAC_NEGATIVE
    return DMAC_NEUTRAL


def _header_html(subject: str, intro: str, logo_path: str = "") -> str:
    logo_html = get_logo_img_tag(logo_path, width=48)
    subtitle = (
        f"<div style=\"font-size: 12px; color: {DMAC_BRAND_ACCENT}; margin-top: 4px;"
        " letter-spacing: 0.06em; text-transform: uppercase;\">"
        "Data Market Analysis Club UDD</div>"
    )
    return (
        "<tr><td style=\"background: linear-gradient(135deg, "
        f"{DMAC_BRAND_PRIMARY} 0%, {DMAC_BRAND_PRIMARY_DARK} 100%);"
        " padding: 28px 24px;\">"
        f"{logo_html}"
        "<div style=\"font-size: 11px; color: rgba(255,255,255,0.85);"
        " letter-spacing: 0.1em; text-transform: uppercase; font-weight: 600;\">DMAC Brief</div>"
        f"<h1 style=\"margin: 6px 0 0 0; font-size: 22px; color: #ffffff; font-weight: 700;\">"
        f"{escape(subject)}</h1>"
        f"{subtitle}"
        f"<p style=\"margin: 14px 0 0 0; color: rgba(255,255,255,0.92); font-size: 13px;"
        f" line-height: 1.55;\">{escape(intro)}</p>"
        "</td></tr>"
    )


def _footer_html() -> str:
    return (
        "<tr><td style=\"padding: 24px; border-top: 1px solid "
        f"{DMAC_BORDER}; background: {DMAC_BG};\">"
        "<p style=\"margin: 0; font-size: 11px; color: "
        f"{DMAC_MUTED}; line-height: 1.55;\">"
        "Reporte generado automaticamente por <strong>DMAC Market Brief Agent</strong>."
        " Hechos observados se basan en titulares publicos y precios de mercado al momento"
        " del envío. Cualquier interpretacion es preliminar y no constituye"
        " recomendacion de inversion.</p>"
        f"<p style=\"margin: 12px 0 0 0; font-size: 13px; color: {DMAC_TEXT};"
        " font-weight: 600; line-height: 1.4;\">Nix Assistant, DMAC UDD.</p>"
        f"<p style=\"margin: 2px 0 0 0; font-size: 12px; color: {DMAC_MUTED};"
        " line-height: 1.4;\">Equipo de Datos y Coyuntura.</p>"
        f"<p style=\"margin: 12px 0 0 0; font-size: 11px; color: {DMAC_MUTED};\">"
        f"&copy; {__import__('datetime').datetime.now().year} Data Market Analysis Club UDD</p>"
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
    include_charts: bool = True,
    nix_analysis_html: str | None = None,
    nix_chart_pngs: dict[str, bytes] | None = None,
    include_deterministic_brief: bool = True,
    market_sentiment=None,
) -> str:
    """Build a professional HTML email from text body, snapshots, and AI analysis.

    Charts are rendered as static HTML/CSS (no JavaScript) so they survive every
    email client. If `nix_analysis_html` is provided, it is rendered as a
    dedicated 'Analisis de Nix' card at the TOP of the body (so it stands out
    from the deterministic data below). When `include_deterministic_brief` is
    False, the parsed "N. Title" sections from `text_body` are skipped (the
    intro line is still extracted for the header).
    """
    from services.email_charts import (
        render_assets_table as _render_assets_table,
    )
    from services.email_charts import (
        render_news_distribution_bars as _render_news_distribution_bars,
    )

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
        section_rows.append(
            _nix_analysis_section(nix_analysis_html, nix_chart_pngs),
        )

    sentiment_html = render_market_sentiment_section(market_sentiment)
    if sentiment_html:
        section_rows.append(sentiment_html)

    if include_deterministic_brief:
        section_rows.extend(
            _render_section_html(block, links=news_link_map or {})
            for block in body_blocks
        )

    if include_charts and snapshots:
        section_rows.append(_render_assets_table(snapshots))
        if news_items:
            dist = _render_news_distribution_bars(news_items, by="region")
            if dist:
                section_rows.append(dist)

    if news_items:
        news_html = render_news_list(news_title, news_items, logo_path=logo_path)
        if news_html:
            section_rows.append(news_html)

    body_html = "".join(section_rows) or (
        f"<tr><td style=\"padding: 24px; color: {DMAC_MUTED};\">"
        "Sin contenido relevante para esta corrida.</td></tr>"
    )

    return (
        "<!doctype html><html lang=\"es\"><head>"
        "<meta charset=\"utf-8\">"
        f"<title>{escape(subject)}</title>"
        "</head><body style=\"margin: 0; padding: 0; background: " + DMAC_BG + ";\">"
        "<table role=\"presentation\" cellspacing=\"0\" cellpadding=\"0\" border=\"0\""
        " style=\"width: 100%; background: " + DMAC_BG + ";\"><tr><td align=\"center\""
        " style=\"padding: 24px 12px;\">"
        "<table role=\"presentation\" cellspacing=\"0\" cellpadding=\"0\" border=\"0\""
        " style=\"width: 100%; max-width: 640px; background: " + DMAC_CARD + ";"
        " border: 1px solid " + DMAC_BORDER + "; border-radius: 8px; overflow: hidden;\">"
        f"{_header_html(subject, intro_text, logo_path=logo_path)}"
        f"{body_html}"
        f"{_footer_html()}"
        "</table></td></tr></table></body></html>"
    )


def _nix_analysis_section(
    html: str,
    nix_chart_pngs: dict[str, bytes] | None = None,
) -> str:
    """Wrap a Nix AI analysis block in a heavy, prominent email card.

    The `html` argument is rendered as trusted HTML (caller is responsible for
    sanitising it first). The card uses a brand-coloured header band with a
    bold title, a "Generado por Ollama Cloud / DMAC AI" eyebrow, and the
    editorial content below.

    `nix_chart_pngs` is accepted for backward compatibility but ignored in the
    MVP: AI-suggested charts are NOT embedded in the productive email. The
    rendering code (`services.ai.chart_renderer.render_charts_as_png`) remains
    available for future use; the static JS-free visuals in the email body
    (asset table, market sentiment, news distribution) cover visualisation needs
    for now.
    """
    del nix_chart_pngs  # intentionally unused in MVP
    fallback_html = (
        "<p style=\"margin: 0; color: " + DMAC_MUTED + ";\">"
        "<em>Analisis de Nix no disponible para esta corrida.</em></p>"
    )
    nix_content: str = html if html.strip() else fallback_html

    return (
        "<tr><td style=\"padding: 24px 24px 0 24px;\">"
        "<table role=\"presentation\" cellspacing=\"0\" cellpadding=\"0\" border=\"0\""
        f" style=\"width: 100%; border-collapse: collapse; background: {DMAC_CARD};"
        f" border: 1px solid {DMAC_BRAND_PRIMARY};"
        f" border-left: 6px solid {DMAC_BRAND_PRIMARY};"
        " border-radius: 8px; overflow: hidden;\">"
        "<tr><td style=\"background: linear-gradient(135deg,"
        f" {DMAC_BRAND_PRIMARY} 0%, {DMAC_BRAND_PRIMARY_DARK} 100%);"
        " padding: 16px 18px;\">"
        "<div style=\"display: inline-block; padding: 3px 9px; background:"
        f" rgba(255,255,255,0.18); color: #ffffff; font-size: 9px;"
        " letter-spacing: 0.12em; text-transform: uppercase; font-weight: 700;"
        " border-radius: 999px;\">DMAC AI</div>"
        f"<h2 style=\"margin: 8px 0 2px 0; font-size: 18px; color: #ffffff;"
        " font-weight: 700; letter-spacing: 0.01em;\">Analisis de Nix</h2>"
        f"<div style=\"font-size: 10px; color: rgba(255,255,255,0.85);"
        " letter-spacing: 0.08em; text-transform: uppercase;\">"
        "Generado por Nix Assistant / DMAC AI</div>"
        "</td></tr>"
        f"<tr><td style=\"padding: 14px 18px 16px 18px; color: {DMAC_TEXT};"
        f" font-size: 13px; line-height: 1.6;\">" + nix_content + "</td></tr>"
        "</table></td></tr>"
    )


def text_to_html(text_body: str) -> str:
    """Convert plain text to a simple, styled HTML preview (no assets/charts)."""
    return build_email_html(
        subject="DMAC Brief",
        text_body=text_body,
    )
