import re
import unicodedata
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

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


@lru_cache(maxsize=1024)
def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"\s+", " ", value.lower()).strip()
    return value


TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_NAMES = {"fbclid", "gclid", "mc_cid", "mc_eid", "ref", "ref_src"}


def canonicalize_url(value: str) -> str:
    parsed = urlparse(value.strip())
    if not parsed.scheme or not parsed.netloc:
        return value.strip()

    query = [
        (key, val)
        for key, val in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_NAMES
        and not any(key.lower().startswith(prefix) for prefix in TRACKING_QUERY_PREFIXES)
    ]
    path = parsed.path.rstrip("/") or "/"
    return urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            "",
            urlencode(query, doseq=True),
            "",
        )
    )


def normalize_title(value: str) -> str:
    value = normalize_text(value)
    value = re.sub(r"[^a-z0-9 ]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


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


@lru_cache(maxsize=512)
def _similarity_ratio(left: str, right: str) -> float:
    return SequenceMatcher(None, normalize_text(left), normalize_text(right)).ratio()


def is_similar_title(left: str, right: str, threshold: float = 0.88) -> bool:
    return _similarity_ratio(normalize_title(left), normalize_title(right)) >= threshold


def deduplicate_news(items: Iterable[RawNewsItem]) -> list[RawNewsItem]:
    seen_urls: set[str] = set()
    unique: list[RawNewsItem] = []
    for item in items:
        canonical_url = canonicalize_url(item.url)
        if canonical_url in seen_urls:
            continue
        if any(is_similar_title(item.title, existing.title, threshold=0.84) for existing in unique):
            continue
        seen_urls.add(canonical_url)
        unique.append(
            RawNewsItem(
                timestamp=item.timestamp,
                source=item.source,
                title=item.title,
                url=canonical_url,
                summary=item.summary,
            )
        )
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
