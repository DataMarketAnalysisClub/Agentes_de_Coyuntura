import calendar
import html
import logging
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import feedparser

from app.config import Settings, get_settings
from app.http_client import CircuitBreakerError, ResilientHttpClient

logger = logging.getLogger(__name__)

RSS_FEED_TIMEOUT = 20.0
RSS_MAX_WORKERS = 8
RSS_MAX_ITEMS_PER_FEED = 30

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


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
    # Etiquetas del medio (categorias RSS y, en DF, `df:tagnames`): ayudan a
    # clasificar el tema. Solo en memoria; no se muestran ni se guardan.
    tags: tuple[str, ...] = field(default=(), compare=False)


DEFAULT_RSS_FEEDS: tuple[RssFeed, ...] = (
    RssFeed("Federal Reserve", "https://www.federalreserve.gov/feeds/press_all.xml"),
    RssFeed("ECB", "https://www.ecb.europa.eu/rss/press.html"),
    RssFeed("Financial Times", "https://www.ft.com/rss/home/international"),
    RssFeed("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
    RssFeed("Investing.com", "https://www.investing.com/rss/news.rss"),
)


@dataclass(frozen=True)
class _CachedFeed:
    etag: str
    last_modified: str
    items: tuple[RawNewsItem, ...]


# GET condicional: por URL, los validadores y las notas de la ultima descarga.
# Vive lo que el proceso (el scheduler corre dias); el monitor de alto impacto
# pide los mismos feeds cada 15 minutos y la mayoria no cambia entre corridas.
_FEED_CACHE: dict[str, _CachedFeed] = {}
_FEED_CACHE_LOCK = threading.Lock()


def clear_feed_cache() -> None:
    with _FEED_CACHE_LOCK:
        _FEED_CACHE.clear()


def fetch_feed(
    http_client, url: str, source: str, max_items: int = RSS_MAX_ITEMS_PER_FEED
) -> list[RawNewsItem]:
    """Descarga y parsea un feed con `If-None-Match`/`If-Modified-Since`.

    Si el servidor responde 304, devuelve las notas de la descarga anterior
    (con sus fechas reales: la salud de fuentes sigue viendo su frescura).
    Feeds sin `ETag` ni `Last-Modified` (DF) se piden completos siempre.
    """
    with _FEED_CACHE_LOCK:
        cached = _FEED_CACHE.get(url)
    headers = {}
    if cached is not None:
        if cached.etag:
            headers["If-None-Match"] = cached.etag
        if cached.last_modified:
            headers["If-Modified-Since"] = cached.last_modified
    response = http_client.get(url, headers=headers) if headers else http_client.get(url)
    if cached is not None and getattr(response, "status_code", 200) == 304:
        logger.info("RSS feed not modified, reusing cached items", extra={"source": source})
        return list(cached.items)

    items = parse_feed(response.content, source, max_items)
    response_headers = getattr(response, "headers", None) or {}
    etag = response_headers.get("etag", "")
    last_modified = response_headers.get("last-modified", "")
    with _FEED_CACHE_LOCK:
        if items and (etag or last_modified):
            _FEED_CACHE[url] = _CachedFeed(etag, last_modified, tuple(items))
        else:
            _FEED_CACHE.pop(url, None)
    return items


def _feed_from_url(url: str) -> RssFeed:
    host = urlparse(url).netloc or url
    return RssFeed(host, url)


class RssNewsClient:
    """RSS client for configurable macro and market news sources."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._http_clients: dict[str, ResilientHttpClient] = {}

    def http_client_for(self, feed: RssFeed) -> ResilientHttpClient:
        # Un circuit breaker por host, no uno global "rss": pybreaker mantiene
        # un lock durante toda la llamada, asi que un breaker compartido
        # serializaba las descargas paralelas; ademas, 5 fallas de un feed
        # caido abrian el circuito para todos los demas.
        host = urlparse(feed.url).netloc or feed.url
        if host not in self._http_clients:
            self._http_clients[host] = ResilientHttpClient(
                name=f"rss:{host}",
                timeout=RSS_FEED_TIMEOUT,
                retries=2,
            )
        return self._http_clients[host]

    def configured_feeds(self) -> tuple[RssFeed, ...]:
        if self.settings.rss_feeds_list:
            return tuple(_feed_from_url(url) for url in self.settings.rss_feeds_list)
        return DEFAULT_RSS_FEEDS

    def fetch_latest(self) -> list[RawNewsItem]:
        # Los feeds son independientes: se piden en paralelo para que el
        # tiempo total quede acotado por el feed mas lento y no por la suma.
        feeds = self.configured_feeds()
        if not feeds:
            return []
        # Crear los clientes antes de lanzar los hilos evita carreras en el dict.
        for feed in feeds:
            self.http_client_for(feed)
        with ThreadPoolExecutor(max_workers=min(RSS_MAX_WORKERS, len(feeds))) as executor:
            results = list(executor.map(self._fetch_feed_safely, feeds))
        return [item for feed_items in results for item in feed_items]

    def _fetch_feed_safely(self, feed: RssFeed) -> list[RawNewsItem]:
        started = time.monotonic()
        try:
            items = self._fetch_single_feed(feed)
        except CircuitBreakerError:
            logger.warning(
                "Circuit breaker open for RSS feed, skipping",
                extra={"source": feed.source},
            )
            return []
        except Exception as exc:
            logger.warning(
                "Failed to fetch RSS feed",
                extra={"source": feed.source, "error_type": type(exc).__name__, "error": str(exc)},
            )
            return []
        logger.info(
            "RSS feed fetched",
            extra={
                "source": feed.source,
                "count": len(items),
                "duration_ms": int((time.monotonic() - started) * 1000),
            },
        )
        return items

    def _fetch_single_feed(self, feed: RssFeed) -> list[RawNewsItem]:
        # Antes, si la request fallaba se reintentaba con feedparser.parse(url),
        # que hace su propia descarga sin timeout ni circuit breaker: duplicaba
        # la espera en feeds caidos. Ahora el error se propaga y se omite el feed.
        return fetch_feed(self.http_client_for(feed), feed.url, feed.source)

    @staticmethod
    def _entry_timestamp(entry: object) -> datetime:
        return entry_timestamp(entry)


def parse_feed(content: bytes | str, source: str, max_items: int = RSS_MAX_ITEMS_PER_FEED) -> list[RawNewsItem]:
    parsed = feedparser.parse(content)

    if getattr(parsed, "bozo", False) and not parsed.entries:
        logger.warning("RSS feed returned parse warning", extra={"source": source})

    items: list[RawNewsItem] = []
    for entry in parsed.entries[:max_items]:
        title = clean_text(str(getattr(entry, "title", "")))
        url = str(getattr(entry, "link", "")).strip()
        if not title or not url:
            continue
        summary = clean_text(str(getattr(entry, "summary", "")))
        items.append(RawNewsItem(entry_timestamp(entry), source, title, url, summary, entry_tags(entry)))
    return items


def entry_tags(entry: object) -> tuple[str, ...]:
    """Categorias RSS (`<category>`) y palabras clave de DF (`<df:tagnames>`)."""
    terms = [str(tag.get("term", "")) for tag in getattr(entry, "tags", None) or []]
    terms += str(getattr(entry, "df_tagnames", "") or "").split(",")
    seen: dict[str, None] = {}
    for term in terms:
        cleaned = clean_text(term)
        if cleaned:
            seen.setdefault(cleaned, None)
    return tuple(seen)


def clean_text(value: str) -> str:
    """Quita tags HTML y entidades que algunos feeds meten en titulo/resumen."""
    text = html.unescape(_HTML_TAG_RE.sub(" ", value))
    return _WHITESPACE_RE.sub(" ", text).strip()


def entry_timestamp(entry: object) -> datetime:
    # feedparser ya normaliza a UTC formatos que parsedate_to_datetime no
    # entiende (ej. Investing.com publica "2026-09-28 19:32:38", sin RFC 822).
    # Sin esto, esas noticias quedaban con timestamp "ahora" y pasaban siempre
    # el filtro de recencia aunque fueran antiguas.
    for attribute in ("published_parsed", "updated_parsed", "created_parsed"):
        value = getattr(entry, attribute, None)
        if value:
            try:
                return datetime.fromtimestamp(calendar.timegm(value), tz=UTC)
            except (TypeError, ValueError, OverflowError):
                continue

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
