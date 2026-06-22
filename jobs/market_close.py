"""Market close job: collects data, builds styled HTML email, sends it."""

import logging
from html import escape as _escape
from pathlib import Path

from app.config import get_settings
from jobs.common import chile_now, collect_market_and_news, write_output_bundle
from services.ai.editorial_pipeline import run_phase3_pipeline
from services.email_formatter import (
    DMAC_BG,
    DMAC_BRAND_PRIMARY,
    build_email_html,
)
from services.email_sender import EmailSender
from services.summarizer import generate_market_close
from services.whatsapp_formatter import format_whatsapp_brief
from storage.models import Brief
from storage.repositories import BriefRepository

logger = logging.getLogger(__name__)


def _build_news_link_map(news) -> dict[str, str]:
    return {n.title: n.url for n in news if n.title and n.url}


def _generate_nix_analysis(
    news,
    snapshots,
    settings,
) -> tuple[str, dict[str, bytes]]:
    """Run the AI editorial pipeline and return sanitized HTML + PNG charts.

    Returns (html, chart_pngs) where html is empty if AI is unavailable, and
    chart_pngs maps chart_id -> PNG bytes (empty when AI is unavailable).
    """
    if not settings.ai_brief_enabled or not settings.ai_enabled:
        return "", {}
    try:
        result = run_phase3_pipeline(
            news_items=news,
            snapshots=snapshots,
            max_news=settings.ai_max_news_items,
            max_per_group=settings.ai_max_news_per_group,
            max_groups=settings.ai_max_groups,
            render_charts_enabled=settings.ai_charts_enabled,
            max_charts=settings.ai_max_charts,
        )
    except Exception as exc:
        logger.warning("Nix AI analysis failed: %s", exc)
        return "", {}
    if not result.editorial:
        return "", {}

    email = result.editorial
    parts: list[str] = []
    if email.executive_summary:
        items = "".join(
            f"<li style=\"margin: 0 0 4px 0;\">{_escape(point)}</li>"
            for point in email.executive_summary[:4]
        )
        parts.append(
            f"<div style=\"margin: 0 0 10px 0;\"><strong style=\"color: {DMAC_BRAND_PRIMARY};\">"
            "Resumen ejecutivo:</strong><ul style=\"margin: 6px 0 0 0; padding-left: 18px;\">"
            f"{items}</ul></div>"
        )
    for section in email.sections:
        if section.heading and section.heading.lower() in {"visualizaciones", "a vigilar", "fuentes", "cautelas editoriales"}:
            continue
        body_html = "".join(
            f"<p style=\"margin: 0 0 8px 0; line-height: 1.5;\">{_escape(line)}</p>"
            for line in section.body
        )
        bullets = "".join(
            f"<li style=\"margin: 0 0 3px 0;\">{_escape(b)}</li>"
            for b in section.bullets[:5]
        )
        section_html = (
            f"<div style=\"margin: 0 0 12px 0;\">"
            f"<h3 style=\"margin: 0 0 6px 0; font-size: 12px; color: {DMAC_BRAND_PRIMARY};"
            f" text-transform: uppercase; letter-spacing: 0.04em;\">{_escape(section.heading)}</h3>"
            f"{body_html}"
        )
        if bullets:
            section_html += f"<ul style=\"margin: 4px 0 0 0; padding-left: 18px;\">{bullets}</ul>"
        section_html += "</div>"
        parts.append(section_html)
    if email.risk_flags:
        items = "".join(
            f"<li style=\"margin: 0 0 4px 0;\">{_escape(flag)}</li>"
            for flag in email.risk_flags[:5]
        )
        parts.append(
            f"<div style=\"margin: 0 0 8px 0;\"><strong style=\"color: {DMAC_BRAND_PRIMARY};\">"
            f"A vigilar:</strong><ul style=\"margin: 6px 0 0 0; padding-left: 18px;\">{items}</ul></div>"
        )
    if email.editorial_cautions:
        items = "".join(
            f"<li style=\"margin: 0 0 4px 0;\">{_escape(c)}</li>"
            for c in email.editorial_cautions[:3]
        )
        parts.append(
            f"<div style=\"margin: 8px 0 0 0; padding: 8px 10px; background: {DMAC_BG};"
            f" border-left: 3px solid {DMAC_BRAND_PRIMARY}; font-size: 11px;\">"
            f"<strong style=\"color: {DMAC_BRAND_PRIMARY};\">Cautelas:</strong>"
            f"<ul style=\"margin: 4px 0 0 0; padding-left: 18px;\">{items}</ul></div>"
        )
    return "".join(parts) or "", result.chart_pngs


def _build_nix_charts_cid_map(chart_pngs: dict[str, bytes]) -> dict[str, bytes]:
    """MVP: AI-suggested charts are NOT embedded in the productive email.

    The pipeline still renders them (cost is small, useful for the AI-phase3
    preview) but the job discards them here. Re-enable by returning
    `chart_pngs` and updating `_nix_analysis_section` to embed base64.
    """
    del chart_pngs  # intentionally discarded in MVP
    return {}


def run_market_close() -> Brief:
    """Generate, persist and optionally email the DMAC Market Close."""
    settings = get_settings()
    now = chile_now(settings)
    snapshots, news = collect_market_and_news(news_hours=24)

    generated = generate_market_close(now.date(), snapshots, news)
    top_news = [n for n in news if n.impact_score][:5]
    nix_analysis_html, nix_chart_pngs = _generate_nix_analysis(news, snapshots, settings)
    nix_charts_inline = _build_nix_charts_cid_map(nix_chart_pngs)
    html_body = build_email_html(
        generated.subject,
        generated.text_body,
        snapshots=snapshots,
        news_items=top_news,
        news_title="Titulares del cierre",
        brief_kind="market close",
        news_link_map=_build_news_link_map(news),
        logo_path=settings.email_logo_path,
        nix_analysis_html=nix_analysis_html or None,
        nix_chart_pngs=nix_charts_inline or None,
        include_deterministic_brief=not bool(nix_analysis_html),
    )
    whatsapp_body = format_whatsapp_brief("Market Close", now.date(), snapshots, news)
    stem = f"market_close_{now:%Y%m%d_%H%M%S}"
    output_path = write_output_bundle(Path("outputs/briefs"), stem, generated.text_body, html_body, whatsapp_body)

    brief = Brief(now, "market_close", generated.subject, generated.text_body, html_body, whatsapp_body, str(output_path))
    BriefRepository().save(brief)
    EmailSender(settings).send(
        generated.subject,
        generated.text_body,
        html_body,
        settings.email_enabled,
    )
    logger.info(
        "Market close generated",
        extra={
            "output_path": str(output_path),
            "nix_analysis": bool(nix_analysis_html),
            "nix_charts_rendered": len(nix_chart_pngs),
            "nix_charts_in_email": len(nix_charts_inline),
        },
    )
    return brief
