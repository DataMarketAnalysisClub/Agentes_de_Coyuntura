"""Render an AiEditorialEmail into a self-contained, email-safe HTML preview.

The formatter composes the editorial structure plus rendered chart fragments
into a single HTML document. Plotly charts use a CDN <script> reference, so
the preview is meant to be opened in a browser (not sent via SMTP yet).
"""

import logging
from html import escape

from services.ai.schemas import AiEditorialEmail

logger = logging.getLogger(__name__)


def render_editorial_email_html(
    email: AiEditorialEmail,
    chart_fragments: dict[str, str] | None = None,
) -> str:
    """Render the editorial email as a standalone HTML document."""
    fragments = chart_fragments or {}

    parts: list[str] = []
    parts.append('<!doctype html>')
    parts.append('<html lang="es">')
    parts.append('<head>')
    parts.append('<meta charset="utf-8">')
    parts.append(f'<title>{escape(email.subject)}</title>')
    parts.append('</head>')
    parts.append(
        '<body style="font-family: Arial, sans-serif; line-height: 1.5; '
        'color: #111827; max-width: 720px; margin: 0 auto; padding: 16px;">'
    )

    parts.append(f'<h1 style="font-size: 22px; margin: 0 0 4px 0;">{escape(email.headline)}</h1>')
    if email.preheader:
        parts.append(
            f'<p style="font-size: 13px; color: #6b7280; margin: 0 0 16px 0;">{escape(email.preheader)}</p>'
        )

    parts.append(_section("Resumen ejecutivo", email.executive_summary))
    if email.market_context:
        parts.append(_section("Contexto de mercado", email.market_context))

    for section in email.sections:
        parts.append(_editorial_section(section.heading, section.body, section.bullets, section.chart_ids, fragments, section.cautions))

    if email.risk_flags:
        parts.append(_section("A vigilar", email.risk_flags))

    if email.source_notes:
        parts.append(_section("Fuentes", email.source_notes))

    if email.editorial_cautions:
        parts.append(_cautions(email.editorial_cautions))

    parts.append(
        '<p style="font-size: 11px; color: #6b7280; margin-top: 24px; '
        'border-top: 1px solid #e5e7eb; padding-top: 8px;">'
        'Reporte editorial automatico. No constituye recomendacion de inversion.'
        '</p>'
    )

    parts.append('</body>')
    parts.append('</html>')
    return "\n".join(parts)


def render_editorial_email_markdown(email: AiEditorialEmail) -> str:
    """Render the editorial email as markdown text (no charts)."""
    lines: list[str] = []
    lines.append(f"# {email.headline}")
    lines.append("")
    if email.preheader:
        lines.append(f"_{email.preheader}_")
        lines.append("")
    lines.append(f"**Asunto:** {email.subject}")
    lines.append("")

    if email.executive_summary:
        lines.append("## Resumen ejecutivo")
        for point in email.executive_summary:
            lines.append(f"- {point}")
        lines.append("")

    if email.market_context:
        lines.append("## Contexto de mercado")
        for point in email.market_context:
            lines.append(f"- {point}")
        lines.append("")

    for section in email.sections:
        lines.append(f"## {section.heading}")
        for para in section.body:
            lines.append(para)
            lines.append("")
        if section.bullets:
            for bullet in section.bullets:
                lines.append(f"- {bullet}")
            lines.append("")
        if section.chart_ids:
            lines.append(f"**Graficos:** {', '.join(section.chart_ids)}")
            lines.append("")
        if section.cautions:
            for caution in section.cautions:
                lines.append(f"> {caution}")
            lines.append("")

    if email.risk_flags:
        lines.append("## A vigilar")
        for flag in email.risk_flags:
            lines.append(f"- {flag}")
        lines.append("")

    if email.source_notes:
        lines.append("## Fuentes")
        for note in email.source_notes:
            lines.append(f"- {note}")
        lines.append("")

    if email.editorial_cautions:
        lines.append("## Cautelas editoriales")
        for caution in email.editorial_cautions:
            lines.append(f"- {caution}")
        lines.append("")

    lines.append("---")
    lines.append("*Reporte editorial automatico. No constituye recomendacion de inversion.*")
    return "\n".join(lines)


def _section(heading: str, items: list[str]) -> str:
    if not items:
        return ""
    inner = "".join(f"<li>{escape(item)}</li>" for item in items)
    return (
        f'<h2 style="font-size: 17px; margin: 20px 0 8px 0;">{escape(heading)}</h2>'
        f'<ul style="margin: 0 0 12px 0; padding-left: 20px;">{inner}</ul>'
    )


def _editorial_section(
    heading: str,
    body: list[str],
    bullets: list[str],
    chart_ids: list[str],
    chart_fragments: dict[str, str],
    cautions: list[str],
) -> str:
    parts: list[str] = []
    parts.append(
        f'<h2 style="font-size: 17px; margin: 20px 0 8px 0; '
        f'border-bottom: 1px solid #e5e7eb; padding-bottom: 4px;">{escape(heading)}</h2>'
    )
    for para in body:
        parts.append(f'<p style="margin: 0 0 12px 0;">{escape(para)}</p>')
    if bullets:
        inner = "".join(f"<li>{escape(b)}</li>" for b in bullets)
        parts.append(
            f'<ul style="margin: 0 0 12px 0; padding-left: 20px;">{inner}</ul>'
        )
    for chart_id in chart_ids:
        fragment = chart_fragments.get(chart_id)
        if fragment:
            parts.append(f'<div style="margin: 12px 0;">{fragment}</div>')
    if cautions:
        items = "".join(f"<li>{escape(c)}</li>" for c in cautions)
        parts.append(
            f'<ul style="margin: 8px 0 12px 0; padding-left: 20px; '
            f'color: #6b7280; font-size: 12px;">{items}</ul>'
        )
    return "".join(parts)


def _cautions(items: list[str]) -> str:
    inner = "".join(f"<li>{escape(item)}</li>" for item in items)
    return (
        '<h2 style="font-size: 15px; margin: 20px 0 8px 0; color: #6b7280;">Cautelas editoriales</h2>'
        f'<ul style="margin: 0 0 12px 0; padding-left: 20px; color: #6b7280; font-size: 12px;">{inner}</ul>'
    )
