import logging
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.config import Settings, get_settings
from data_sources.chile_news_client import ChileNewsClient
from data_sources.rss_news_client import RssNewsClient
from services.impact_scoring import with_impact_scores
from services.market_snapshot import MarketSnapshotService
from services.news_classifier import classify_news, filter_recent_news
from storage.database import init_db
from storage.models import MarketSnapshot, NewsItem
from storage.repositories import MarketSnapshotRepository, NewsRepository

logger = logging.getLogger(__name__)


def chile_now(settings: Settings | None = None) -> datetime:
    current_settings = settings or get_settings()
    return datetime.now(ZoneInfo(current_settings.tz))


def collect_market_and_news(news_hours: int) -> tuple[list[MarketSnapshot], list[NewsItem]]:
    init_db()

    logger.info("Starting data collection", extra={"news_hours": news_hours})

    snapshots = MarketSnapshotService().collect()
    logger.info("Market snapshots collected", extra={"count": len(snapshots)})

    MarketSnapshotRepository().save_many(snapshots)

    rss_news = RssNewsClient().fetch_latest()
    logger.info("RSS news collected", extra={"count": len(rss_news)})

    chile_news = ChileNewsClient().fetch_latest()
    logger.info("Chile news collected", extra={"count": len(chile_news)})

    raw_news = rss_news + chile_news
    logger.info("Total raw news items", extra={"count": len(raw_news)})

    classified = classify_news(raw_news)
    logger.info("News after classification and deduplication", extra={"count": len(classified)})

    recent = filter_recent_news(classified, news_hours, datetime.now(UTC))
    logger.info("News after time filter", extra={"hours": news_hours, "count": len(recent)})

    scored = with_impact_scores(recent, snapshots)
    logger.info("News after impact scoring", extra={"count": len(scored)})

    NewsRepository().save_many(scored)

    high_impact = [n for n in scored if n.impact_score and n.impact_score >= 8]
    logger.info(
        "High impact news",
        extra={"total": len(scored), "high_impact": len(high_impact)},
    )

    return snapshots, scored


def write_output_bundle(
    directory: Path,
    stem: str,
    text_body: str,
    html_body: str,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    text_path = directory / f"{stem}.txt"
    html_path = directory / f"{stem}.html"

    text_path.write_text(text_body, encoding="utf-8")
    html_path.write_text(html_body, encoding="utf-8")
    return text_path
