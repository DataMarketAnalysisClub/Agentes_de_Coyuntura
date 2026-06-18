import logging
from pathlib import Path

from app.config import get_settings
from jobs.common import chile_now, collect_market_and_news, write_output_bundle
from services.email_formatter import build_email_html
from services.email_sender import EmailSender
from services.summarizer import generate_morning_brief
from services.whatsapp_formatter import format_whatsapp_brief
from storage.models import Brief
from storage.repositories import BriefRepository

logger = logging.getLogger(__name__)


def run_morning_brief() -> Brief:
    """Generate, persist and optionally email the DMAC Morning Brief."""

    settings = get_settings()
    now = chile_now(settings)
    snapshots, news = collect_market_and_news(news_hours=18)

    generated = generate_morning_brief(now.date(), snapshots, news)
    html_body = build_email_html(generated.subject, generated.text_body)
    whatsapp_body = format_whatsapp_brief("Morning Brief", now.date(), snapshots, news)
    stem = f"morning_brief_{now:%Y%m%d_%H%M%S}"
    output_path = write_output_bundle(
        directory=Path("outputs/briefs"),
        stem=stem,
        text_body=generated.text_body,
        html_body=html_body,
        whatsapp_body=whatsapp_body,
    )

    brief = Brief(now, "morning", generated.subject, generated.text_body, html_body, whatsapp_body, str(output_path))
    BriefRepository().save(brief)
    EmailSender(settings).send(generated.subject, generated.text_body, html_body, settings.email_enabled)
    logger.info("Morning brief generated", extra={"output_path": str(output_path)})
    return brief
