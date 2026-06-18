from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.config import Settings, get_settings
from data_sources.rss_news_client import RssNewsClient
from services.impact_scoring import with_impact_scores
from services.market_snapshot import MarketSnapshotService
from services.news_classifier import classify_news, filter_recent_news
from storage.database import init_db
from storage.models import MarketSnapshot, NewsItem
from storage.repositories import MarketSnapshotRepository, NewsRepository


def chile_now(settings: Settings | None = None) -> datetime:
    current_settings = settings or get_settings()
    return datetime.now(ZoneInfo(current_settings.tz))


def collect_market_and_news(news_hours: int) -> tuple[list[MarketSnapshot], list[NewsItem]]:
    init_db()
    snapshots = MarketSnapshotService().collect()
    MarketSnapshotRepository().save_many(snapshots)

    raw_news = RssNewsClient().fetch_latest()
    classified = classify_news(raw_news)
    recent = filter_recent_news(classified, news_hours, datetime.now(UTC))
    scored = with_impact_scores(recent, snapshots)
    NewsRepository().save_many(scored)
    return snapshots, scored


def write_output_bundle(
    directory: Path,
    stem: str,
    text_body: str,
    html_body: str,
    whatsapp_body: str,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    text_path = directory / f"{stem}.txt"
    html_path = directory / f"{stem}.html"
    whatsapp_path = Path("outputs/whatsapp") / f"{stem}.txt"
    whatsapp_path.parent.mkdir(parents=True, exist_ok=True)

    text_path.write_text(text_body, encoding="utf-8")
    html_path.write_text(html_body, encoding="utf-8")
    whatsapp_path.write_text(whatsapp_body, encoding="utf-8")
    return text_path
