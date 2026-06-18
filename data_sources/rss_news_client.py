import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import feedparser

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RssFeed:
    source: str
    url: str


@dataclass(frozen=True)
class RawNewsItem:
    timestamp: datetime
    source: str
    title: str
    url: str
    summary: str


DEFAULT_RSS_FEEDS: tuple[RssFeed, ...] = (
    RssFeed("Banco Central de Chile", "https://www.bcentral.cl/web/banco-central/rss"),
    RssFeed("CMF Chile", "https://www.cmfchile.cl/portal/prensa/rss.xml"),
    RssFeed("INE Chile", "https://www.ine.gob.cl/rss"),
    RssFeed("Ministerio de Hacienda Chile", "https://www.hacienda.cl/rss"),
    RssFeed("Federal Reserve", "https://www.federalreserve.gov/feeds/press_all.xml"),
    RssFeed("BLS", "https://www.bls.gov/feeds/news_release/bls_latest.rss"),
    RssFeed("BEA", "https://www.bea.gov/news/glance/rss"),
    RssFeed("ECB", "https://www.ecb.europa.eu/rss/press.html"),
    RssFeed("IMF", "https://www.imf.org/en/News/RSS"),
    RssFeed("World Bank", "https://www.worldbank.org/en/news/all/rss"),
)


def _feed_from_url(url: str) -> RssFeed:
    host = urlparse(url).netloc or url
    return RssFeed(host, url)


class RssNewsClient:
    """RSS client for configurable macro and market news sources."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def configured_feeds(self) -> tuple[RssFeed, ...]:
        if self.settings.rss_feeds:
            return tuple(_feed_from_url(url) for url in self.settings.rss_feeds)
        return DEFAULT_RSS_FEEDS

    def fetch_latest(self) -> list[RawNewsItem]:
        items: list[RawNewsItem] = []
        for feed in self.configured_feeds():
            try:
                parsed = feedparser.parse(feed.url)
                if getattr(parsed, "bozo", False):
                    logger.warning("RSS feed returned parse warning", extra={"source": feed.source})
                for entry in parsed.entries[:30]:
                    title = str(getattr(entry, "title", "")).strip()
                    url = str(getattr(entry, "link", "")).strip()
                    if not title or not url:
                        continue
                    summary = str(getattr(entry, "summary", "")).strip()
                    timestamp = self._entry_timestamp(entry)
                    items.append(RawNewsItem(timestamp, feed.source, title, url, summary))
            except Exception:
                logger.warning("Failed to fetch RSS feed", extra={"source": feed.source}, exc_info=True)
        return items

    @staticmethod
    def _entry_timestamp(entry: object) -> datetime:
        for attribute in ("published", "updated", "created"):
            value = getattr(entry, attribute, None)
            if not value:
                continue
            try:
                parsed = parsedate_to_datetime(str(value))
                if parsed.tzinfo is None:
                    return parsed.replace(tzinfo=UTC)
                return parsed.astimezone(UTC)
            except (TypeError, ValueError):
                continue
        return datetime.now(UTC)
