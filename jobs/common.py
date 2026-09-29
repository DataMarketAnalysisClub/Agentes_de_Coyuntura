import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.config import Settings, get_settings
from data_sources.chile_news_client import ChileNewsClient
from data_sources.rss_news_client import RssNewsClient
from services.impact_scoring import with_impact_scores
from services.market_snapshot import MarketSnapshotService
from services.news_classifier import classify_news
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

    # Mercado (yfinance + BCCh), RSS y scraping Chile son 3 llamadas HTTP
    # independientes entre si: corrian en serie antes, lo que sumaba su
    # latencia. En paralelo, el tiempo total queda acotado por la mas lenta
    # de las tres en vez de la suma.
    with ThreadPoolExecutor(max_workers=3) as executor:
        snapshots_future = executor.submit(MarketSnapshotService().collect)
        rss_future = executor.submit(RssNewsClient().fetch_latest)
        chile_future = executor.submit(ChileNewsClient().fetch_latest)

        snapshots = snapshots_future.result()
        logger.info("Market snapshots collected", extra={"count": len(snapshots)})

        rss_news = rss_future.result()
        logger.info("RSS news collected", extra={"count": len(rss_news)})

        chile_news = chile_future.result()
        logger.info("Chile news collected", extra={"count": len(chile_news)})

    MarketSnapshotRepository().save_many(snapshots)

    raw_news = rss_news + chile_news
    logger.info("Total raw news items", extra={"count": len(raw_news)})

    # Filtrar por recencia ANTES de deduplicar: la deduplicacion es O(n^2)
    # por similitud de titulos y, si una nota vieja llegaba primero, podia
    # descartar a su version reciente y luego ser eliminada por el filtro de
    # tiempo, perdiendo ambas.
    since = datetime.now(UTC) - timedelta(hours=news_hours)
    recent_raw = [item for item in raw_news if item.timestamp >= since]
    logger.info("News after time filter", extra={"hours": news_hours, "count": len(recent_raw)})

    recent = classify_news(recent_raw)
    logger.info("News after classification and deduplication", extra={"count": len(recent)})

    scored = with_impact_scores(recent, snapshots)
    logger.info("News after impact scoring", extra={"count": len(scored)})

    NewsRepository().save_many(scored)

    threshold = get_settings().high_impact_threshold
    high_impact = [n for n in scored if n.impact_score and n.impact_score >= threshold]
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
