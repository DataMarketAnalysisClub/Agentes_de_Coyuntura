"""High impact monitor: detects extreme news and sends styled alert emails."""

import logging
from pathlib import Path

from app.config import get_settings
from jobs.common import chile_now, collect_market_and_news
from services.email_formatter import build_email_html
from services.email_sender import EmailSender
from services.summarizer import generate_alert_text
from storage.models import Alert
from storage.repositories import AlertRepository

logger = logging.getLogger(__name__)


def _render_alert_html(
    subject: str,
    text_body: str,
    snapshots,
    news_items: list,
    logo_path: str,
) -> str:
    link_map = (
        {n.title: n.url for n in news_items if n.title and n.url}
        if news_items
        else {}
    )
    return build_email_html(
        subject=subject,
        text_body=text_body,
        snapshots=snapshots,
        news_items=news_items,
        news_title="Noticia gatillante",
        brief_kind="alerta de alto impacto",
        news_link_map=link_map,
        logo_path=logo_path,
    )


def run_high_impact_monitor_once() -> list[Alert]:
    """Evaluate recent market/news data and generate deduplicated high impact alerts."""
    settings = get_settings()
    now = chile_now(settings)
    snapshots, news = collect_market_and_news(news_hours=3)
    repository = AlertRepository()
    alerts: list[Alert] = []

    for item in sorted(news, key=lambda entry: entry.impact_score, reverse=True):
        if item.impact_score < settings.high_impact_threshold:
            continue
        if repository.exists_recent(item.title, now, settings.alert_dedup_hours):
            logger.info("Skipping duplicate high impact alert", extra={"title": item.title})
            continue

        text_body = generate_alert_text(item, snapshots)
        subject = f"DMAC Alert | Alto impacto financiero | {item.title[:80]}"
        html_body = _render_alert_html(
            subject, text_body, snapshots, [item], settings.email_logo_path,
        )
        alert = Alert(now, item.title, item.impact_score, text_body, sent=False)
        output_path = _write_alert(now, item.title, text_body, html_body)
        sent = EmailSender(settings).send(subject, text_body, html_body, settings.alert_email_enabled)
        alert = Alert(alert.timestamp, alert.event_title, alert.impact_score, alert.text_body, sent)
        repository.save(alert)
        alerts.append(alert)
        logger.info("High impact alert generated", extra={"output_path": str(output_path)})

    if not alerts:
        logger.info("No high impact alerts generated")
    return alerts


def _write_alert(now, title: str, text_body: str, html_body: str) -> Path:
    safe_title = "".join(char.lower() if char.isalnum() else "_" for char in title[:40]).strip("_")
    stem = f"alert_{now:%Y%m%d_%H%M%S}_{safe_title or 'event'}"
    directory = Path("outputs/alerts")
    directory.mkdir(parents=True, exist_ok=True)
    text_path = directory / f"{stem}.txt"
    html_path = directory / f"{stem}.html"
    text_path.write_text(text_body, encoding="utf-8")
    html_path.write_text(html_body, encoding="utf-8")
    return text_path
