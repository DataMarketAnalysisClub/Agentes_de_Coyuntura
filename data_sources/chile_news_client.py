import logging
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin

from app.http_client import CircuitBreakerError, ResilientHttpClient
from data_sources.rss_news_client import RawNewsItem

logger = logging.getLogger(__name__)

SCRAPE_TIMEOUT_SECONDS = 15.0


class ChileNewsClient:
    """Scraping client for Chilean news sources."""

    def __init__(self, http_client: ResilientHttpClient | None = None) -> None:
        self._http_client = http_client

    def _get_client(self) -> ResilientHttpClient:
        if self._http_client is None:
            return ResilientHttpClient(
                name="chile_news",
                timeout=SCRAPE_TIMEOUT_SECONDS,
                retries=2,
            )
        return self._http_client

    def close(self) -> None:
        pass

    def fetch_latest(self) -> list[RawNewsItem]:
        items: list[RawNewsItem] = []
        sources = [
            ("Ministerio de Hacienda", self._scrape_hacienda),
            ("La Tercera Pulso", self._scrape_latercera_pulso),
        ]
        for source_name, scraper in sources:
            try:
                scraped = scraper()
                items.extend(scraped)
                logger.info("Scraped %d items from %s", len(scraped), source_name)
            except CircuitBreakerError:
                logger.warning("Circuit breaker open for %s, skipping", source_name)
            except Exception:
                logger.warning("Failed to scrape %s", source_name, exc_info=True)
        return items

    def _scrape_hacienda(self) -> list[RawNewsItem]:
        base_url = "https://www.hacienda.cl"
        items: list[RawNewsItem] = []

        try:
            client = self._get_client()
            response = client.get(f"{base_url}/noticias-y-eventos")
            response.raise_for_status()
        except Exception:
            logger.warning("Failed to fetch Hacienda news page")
            return []

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(response.text, "lxml")
        news_links: list[tuple[str, str, datetime | None]] = []

        for link in soup.select('a[href*="/noticias-y-eventos/noticias/"]'):
            href = link.get("href", "")
            if not href:
                continue
            full_url = urljoin(base_url, href)
            title = link.get_text(strip=True)
            if title and full_url:
                news_links.append((title, full_url, None))

        for title, url, _ in news_links[:10]:
            item = self._fetch_hacienda_article(url, title)
            if item:
                items.append(item)

        return items

    def _fetch_hacienda_article(self, url: str, fallback_title: str) -> RawNewsItem | None:
        try:
            client = self._get_client()
            response = client.get(url)
            response.raise_for_status()
        except Exception:
            logger.warning("Failed to fetch Hacienda article: %s", url)
            return None

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(response.text, "lxml")

        timestamp = self._extract_hacienda_timestamp(soup)
        summary = self._extract_hacienda_summary(soup)

        return RawNewsItem(
            timestamp=timestamp,
            source="Ministerio de Hacienda",
            title=fallback_title,
            url=url,
            summary=summary,
        )

    @staticmethod
    def _extract_hacienda_timestamp(soup: Any) -> datetime:

        time_tag = soup.select_one("article time[datetime], time[datetime], .date")
        if time_tag:
            dt_attr = time_tag.get("datetime") or time_tag.get("data-date")
            if dt_attr:
                try:
                    dt = datetime.fromisoformat(dt_attr.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        return dt.replace(tzinfo=UTC)
                    return dt.astimezone(UTC)
                except ValueError:
                    pass

        date_text = soup.select_one(".fecha, .date, time")
        if date_text:
            date_str = date_text.get_text(strip=True)
            if date_str:
                try:
                    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d de %B de %Y"):
                        try:
                            dt = datetime.strptime(date_str, fmt)
                            return dt.replace(tzinfo=UTC)
                        except ValueError:
                            continue
                except Exception:
                    pass

        return datetime.now(UTC)

    @staticmethod
    def _extract_hacienda_summary(soup: Any) -> str:
        summary_tag = soup.select_one(
            "article p, .contenido p, .field-name-body p, .articulo-contenido p"
        )
        if summary_tag:
            return summary_tag.get_text(strip=True)[:500]
        return ""

    def _scrape_latercera_pulso(self) -> list[RawNewsItem]:
        base_url = "https://www.latercera.com"
        items: list[RawNewsItem] = []

        try:
            client = self._get_client()
            response = client.get(f"{base_url}/canal/pulso/")
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

            if title:
                full_url = urljoin("https://www.latercera.com", href)
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
                    return dt.replace(tzinfo=UTC)
                except ValueError:
                    pass

        return datetime.now(UTC)
