import logging
from pathlib import Path

from app.config import get_settings
from jobs.common import chile_now, collect_market_and_news, write_output_bundle
from services.email_formatter import build_email_html
from services.email_sender import EmailSender
from services.summarizer import generate_market_close
from services.whatsapp_formatter import format_whatsapp_brief
from storage.models import Brief
from storage.repositories import BriefRepository

logger = logging.getLogger(__name__)


def run_market_close() -> Brief:
    """Generate, persist and optionally email the DMAC Market Close."""

    settings = get_settings()
    now = chile_now(settings)
    snapshots, news = collect_market_and_news(news_hours=24)

    generated = generate_market_close(now.date(), snapshots, news)
    html_body = build_email_html(generated.subject, generated.text_body)
    whatsapp_body = format_whatsapp_brief("Market Close", now.date(), snapshots, news)
    stem = f"market_close_{now:%Y%m%d_%H%M%S}"
    output_path = write_output_bundle(Path("outputs/briefs"), stem, generated.text_body, html_body, whatsapp_body)

    brief = Brief(now, "market_close", generated.subject, generated.text_body, html_body, whatsapp_body, str(output_path))
    BriefRepository().save(brief)
    EmailSender(settings).send(generated.subject, generated.text_body, html_body, settings.email_enabled)
    logger.info("Market close generated", extra={"output_path": str(output_path)})
    return brief
