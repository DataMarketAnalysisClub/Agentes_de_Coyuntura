import re
import unicodedata
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher

from data_sources.rss_news_client import RawNewsItem
from storage.models import NewsItem


REGION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Chile": ("chile", "bcch", "banco central de chile", "cmf", "ipc", "imacec", "hacienda"),
    "Latam": ("latam", "brasil", "mexico", "colombia", "peru", "argentina", "bovespa"),
    "EE.UU.": ("fed", "federal reserve", "united states", "eeuu", "u.s.", "us ", "bls", "bea"),
    "Global": ("global", "world", "europe", "ecb", "imf", "china", "geopolit"),
}

TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "tasas": ("tasa", "rate", "yield", "treasury"),
    "inflacion": ("ipc", "inflacion", "inflation", "cpi", "ppi"),
    "actividad": ("pib", "gdp", "imacec", "actividad", "growth"),
    "empleo": ("empleo", "jobs", "payroll", "unemployment", "labor"),
    "commodities": ("cobre", "copper", "oil", "petroleo", "brent", "wti", "gold", "oro"),
    "FX": ("dolar", "dollar", "fx", "currency", "peso"),
    "renta variable": ("acciones", "equity", "stocks", "s&p", "nasdaq", "ipsa"),
    "politica fiscal": ("fiscal", "budget", "deuda", "hacienda", "treasury"),
    "bancos centrales": ("fed", "ecb", "banco central", "central bank", "monetary"),
    "geopolitica": ("war", "guerra", "geopolit", "sanction"),
    "regulacion financiera": ("cmf", "sec", "regulation", "regulacion", "banking"),
    "empresas": ("earnings", "resultados", "company", "empresa"),
}


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"\s+", " ", value.lower()).strip()
    return value


def classify_region(title: str, summary: str = "") -> str:
    text = normalize_text(f"{title} {summary}")
    for region, keywords in REGION_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return region
    return "Global"


def classify_topic(title: str, summary: str = "") -> str:
    text = normalize_text(f"{title} {summary}")
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return topic
    return "macro general"


def is_similar_title(left: str, right: str, threshold: float = 0.88) -> bool:
    return SequenceMatcher(None, normalize_text(left), normalize_text(right)).ratio() >= threshold


def deduplicate_news(items: Iterable[RawNewsItem]) -> list[RawNewsItem]:
    seen_urls: set[str] = set()
    unique: list[RawNewsItem] = []
    for item in items:
        if item.url in seen_urls:
            continue
        if any(is_similar_title(item.title, existing.title) for existing in unique):
            continue
        seen_urls.add(item.url)
        unique.append(item)
    return unique


def classify_news(items: Iterable[RawNewsItem]) -> list[NewsItem]:
    classified: list[NewsItem] = []
    for item in deduplicate_news(items):
        classified.append(
            NewsItem(
                timestamp=item.timestamp,
                source=item.source,
                title=item.title,
                url=item.url,
                summary=item.summary,
                region=classify_region(item.title, item.summary),
                topic=classify_topic(item.title, item.summary),
            )
        )
    return classified


def filter_recent_news(items: Iterable[NewsItem], hours: int = 18, now: datetime | None = None) -> list[NewsItem]:
    reference = now or datetime.now(UTC)
    since = reference - timedelta(hours=hours)
    return [item for item in items if item.timestamp >= since]
