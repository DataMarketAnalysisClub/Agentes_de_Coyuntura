import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

from app.http_client import CircuitBreakerError, ResilientHttpClient
from data_sources.rss_news_client import RawNewsItem, parse_feed

logger = logging.getLogger(__name__)

SCRAPE_TIMEOUT_SECONDS = 15.0
CHILE_TZ = ZoneInfo("America/Santiago")

LATERCERA_BASE_URL = "https://www.latercera.com"
# Feed oficial (Arc Publishing) de la seccion Pulso: ~3x mas liviano que el
# HTML del canal, trae fecha de publicacion real y ~30 notas en vez de 10.
LATERCERA_PULSO_RSS_URL = f"{LATERCERA_BASE_URL}/arc/outboundfeeds/rss/category/pulso/?outputType=xml"
LATERCERA_PULSO_HTML_URL = f"{LATERCERA_BASE_URL}/canal/pulso/"
LATERCERA_MAX_ITEMS = 20

# RSS de portada de Diario Financiero: ~50 notas con fecha. Solo se usan
# titulo, bajada y link del feed (no se descarga el articulo: DF tiene
# paywall). Se conservan las secciones de hechos economicos; Opinion (cartas,
# columnas, editorial), Regiones y suplementos quedan fuera.
DF_RSS_URL = "https://www.df.cl/noticias/site/list/port/rss.xml"
DF_ALLOWED_SECTIONS = frozenset({"mercados", "economia-y-politica", "empresas", "internacional", "primer-click"})
DF_MAX_ITEMS = 20


class ChileNewsClient:
    """Scraping client for Chilean news sources."""

    def __init__(self, http_client: ResilientHttpClient | None = None) -> None:
        self._http_client = http_client

    def _get_client(self, name: str = "chile_news") -> ResilientHttpClient:
        # Un circuit breaker por medio: pybreaker bloquea durante toda la
        # llamada, y uno compartido serializaria las fuentes en paralelo.
        if self._http_client is None:
            return ResilientHttpClient(
                name=name,
                timeout=SCRAPE_TIMEOUT_SECONDS,
                retries=2,
            )
        return self._http_client

    def close(self) -> None:
        pass

    def fetch_latest(self) -> list[RawNewsItem]:
        sources = [
            ("La Tercera Pulso", self._fetch_latercera_pulso),
            ("Diario Financiero", self._fetch_df),
        ]
        with ThreadPoolExecutor(max_workers=len(sources)) as executor:
            futures = [(source_name, executor.submit(scraper)) for source_name, scraper in sources]
        items: list[RawNewsItem] = []
        for source_name, future in futures:
            try:
                scraped = future.result()
                items.extend(scraped)
                logger.info("Scraped %d items from %s", len(scraped), source_name)
            except CircuitBreakerError:
                logger.warning("Circuit breaker open for %s, skipping", source_name)
            except Exception:
                logger.warning("Failed to scrape %s", source_name, exc_info=True)
        return items

    def _fetch_df(self) -> list[RawNewsItem]:
        try:
            response = self._get_client("df_news").get(DF_RSS_URL)
            items = parse_feed(response.content, "Diario Financiero")
        except CircuitBreakerError:
            raise
        except Exception as exc:
            logger.warning(
                "Failed to fetch Diario Financiero RSS",
                extra={"error_type": type(exc).__name__, "error": str(exc)},
            )
            return []
        selected = [
            replace(item, url=item.url.replace("http://", "https://", 1))
            for item in items
            if _df_section(item.url) in DF_ALLOWED_SECTIONS
        ]
        return selected[:DF_MAX_ITEMS]

    def _fetch_latercera_pulso(self) -> list[RawNewsItem]:
        """RSS primero; el scraping del HTML queda solo como respaldo."""
        items = self._fetch_latercera_pulso_rss()
        if items:
            return items
        logger.warning("La Tercera Pulso RSS returned no items, falling back to HTML scraping")
        return self._scrape_latercera_pulso()

    def _fetch_latercera_pulso_rss(self) -> list[RawNewsItem]:
        try:
            response = self._get_client().get(LATERCERA_PULSO_RSS_URL)
            items = parse_feed(response.content, "La Tercera Pulso")
        except CircuitBreakerError:
            raise
        except Exception as exc:
            logger.warning(
                "Failed to fetch La Tercera Pulso RSS",
                extra={"error_type": type(exc).__name__, "error": str(exc)},
            )
            return []
        return [item for item in items if "/pulso/" in item.url][:LATERCERA_MAX_ITEMS]

    def _scrape_latercera_pulso(self) -> list[RawNewsItem]:
        items: list[RawNewsItem] = []

        try:
            client = self._get_client()
            response = client.get(LATERCERA_PULSO_HTML_URL)
            response.raise_for_status()
        except Exception:
            logger.warning("Failed to fetch La Tercera Pulso page")
            return []

        articles = self._extract_latercera_articles(response.text)

        for article_data in articles[:10]:
            url, title, summary, timestamp = article_data
            if not title:
                continue
            items.append(
                RawNewsItem(
                    timestamp=timestamp,
                    source="La Tercera Pulso",
                    title=title,
                    url=url,
                    summary=summary[:500] if summary else "",
                )
            )

        return items

    def _extract_latercera_articles(
        self, html: str
    ) -> list[tuple[str, str, str, datetime]]:
        from bs4 import BeautifulSoup

        results: list[tuple[str, str, str, datetime]] = []
        seen_urls: set[str] = set()
        soup = BeautifulSoup(html, "lxml")

        for article in soup.select("article, .story-card, .c-post"):
            link_tag = article.select_one("a[href]")
            if not link_tag:
                continue
            href = link_tag.get("href", "")
            if not href or "/pulso/" not in href:
                continue

            title_tag = article.select_one("h2, h3, .headline, .c-title")
            title = title_tag.get_text(strip=True) if title_tag else ""

            desc_tag = article.select_one(".description, .c-deck, .summary, p")
            summary = desc_tag.get_text(strip=True) if desc_tag else ""

            timestamp = self._extract_latercera_timestamp(article)

            full_url = urljoin(LATERCERA_BASE_URL, href)
            # Los selectores se solapan (un <article> puede contener un
            # .story-card), asi que la misma nota puede aparecer dos veces.
            if title and full_url not in seen_urls:
                seen_urls.add(full_url)
                results.append((full_url, title, summary, timestamp))

        return results

    @staticmethod
    def _extract_latercera_timestamp(article: Any) -> datetime:

        time_tag = article.select_one("time[datetime], time[date]")
        if time_tag:
            dt_attr = time_tag.get("datetime") or time_tag.get("date")
            if dt_attr:
                try:
                    dt = datetime.fromisoformat(dt_attr.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        return dt.replace(tzinfo=UTC)
                    return dt.astimezone(UTC)
                except ValueError:
                    pass

        pub_date = article.select_one(".publish-date, .date, .c-date")
        if pub_date:
            date_str = pub_date.get_text(strip=True)
            if date_str:
                try:
                    dt = datetime.strptime(date_str, "%d/%m/%Y %H:%M")
                    # La fecha visible del sitio esta en hora de Chile, no UTC.
                    return dt.replace(tzinfo=CHILE_TZ).astimezone(UTC)
                except ValueError:
                    pass

        return datetime.now(UTC)


def _df_section(url: str) -> str:
    """Primer segmento de la ruta: "mercados" en df.cl/mercados/bolsa-monedas/..."""
    return urlparse(url).path.strip("/").split("/", 1)[0]
