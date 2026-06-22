import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import feedparser

from app.config import Settings, get_settings
from app.http_client import CircuitBreakerError, ResilientHttpClient

logger = logging.getLogger(__name__)

RSS_FEED_TIMEOUT = 20.0


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
    RssFeed("Federal Reserve", "https://www.federalreserve.gov/feeds/press_all.xml"),
    RssFeed("ECB", "https://www.ecb.europa.eu/rss/press.html"),
    RssFeed("Financial Times", "https://www.ft.com/rss/home/international"),
    RssFeed("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    RssFeed("Investing.com", "https://www.investing.com/rss/news.rss"),
)


def _feed_from_url(url: str) -> RssFeed:
    host = urlparse(url).netloc or url
    return RssFeed(host, url)


class RssNewsClient:
    """RSS client for configurable macro and market news sources."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._http_client: ResilientHttpClient | None = None

    @property
    def http_client(self) -> ResilientHttpClient:
        if self._http_client is None:
            self._http_client = ResilientHttpClient(
                name="rss",
                timeout=RSS_FEED_TIMEOUT,
                retries=2,
            )
        return self._http_client

    def configured_feeds(self) -> tuple[RssFeed, ...]:
        if self.settings.rss_feeds_list:
            return tuple(_feed_from_url(url) for url in self.settings.rss_feeds_list)
        return DEFAULT_RSS_FEEDS

    def fetch_latest(self) -> list[RawNewsItem]:
        items: list[RawNewsItem] = []
        for feed in self.configured_feeds():
            try:
                feed_items = self._fetch_single_feed(feed)
                items.extend(feed_items)
            except CircuitBreakerError:
                logger.warning(
                    "Circuit breaker open for RSS feed, skipping",
                    extra={"source": feed.source},
                )
            except Exception:
                logger.warning(
                    "Failed to fetch RSS feed",
                    extra={"source": feed.source},
                    exc_info=True,
                )
        return items

    def _fetch_single_feed(self, feed: RssFeed) -> list[RawNewsItem]:
        try:
            response = self.http_client.get(feed.url)
            xml_content = response.text
        except Exception:
            logger.warning(
                "HTTP request failed for RSS feed, trying direct parse",
                extra={"source": feed.source},
            )
            parsed = feedparser.parse(feed.url)
        else:
            parsed = feedparser.parse(xml_content)

        if getattr(parsed, "bozo", False):
            logger.warning(
                "RSS feed returned parse warning",
                extra={"source": feed.source},
            )

        items: list[RawNewsItem] = []
        for entry in parsed.entries[:30]:
            title = str(getattr(entry, "title", "")).strip()
            url = str(getattr(entry, "link", "")).strip()
            if not title or not url:
                continue
            summary = str(getattr(entry, "summary", "")).strip()
            timestamp = self._entry_timestamp(entry)
            items.append(RawNewsItem(timestamp, feed.source, title, url, summary))

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
