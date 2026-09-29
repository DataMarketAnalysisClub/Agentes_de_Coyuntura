import re
import unicodedata
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from difflib import SequenceMatcher
from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from data_sources.rss_news_client import RawNewsItem
from storage.models import NewsItem

# Palabras clave normalizadas (minusculas, sin tildes). Se buscan como
# palabras completas con plural opcional ("tasa" calza con "tasas", "rate" con
# "rates", pero "rate" ya no calza con "corporate" ni "oil" con "turmoil").
# Un "*" final marca un prefijo: "geopolit*" cubre geopolitica/geopolitical.
REGION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Chile": ("chile", "chilen*", "chilean", "bcch", "banco central de chile", "cmf", "ipc", "imacec", "hacienda"),
    "Latam": (
        "latam", "brasil", "brazil*", "mexic*", "colombi*", "peru", "peruan*", "peruvian", "argentin*", "bovespa",
    ),
    "EE.UU.": (
        "fed", "federal reserve", "reserva federal", "fomc", "federal open market committee", "united states",
        "estados unidos", "eeuu", "ee.uu", "u.s", "wall street", "bls", "bea",
    ),
    "Global": ("global", "world", "europe*", "ecb", "imf", "china", "chinese", "geopolit*"),
}

TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "tasas": ("tasa", "rate", "yield", "treasury", "treasuries"),
    "inflacion": ("ipc", "inflacion", "inflation", "cpi", "ppi"),
    "actividad": ("pib", "gdp", "imacec", "actividad", "growth"),
    "empleo": (
        "empleo", "desempleo", "desocupacion", "laboral", "jobs", "payroll", "unemployment", "labor", "labour",
    ),
    "commodities": ("cobre", "copper", "oil", "petroleo", "brent", "wti", "gold", "oro"),
    "FX": ("dolar", "dollar", "fx", "currency", "currencies", "peso"),
    "renta variable": ("acciones", "equity", "equities", "stock", "s&p", "nasdaq", "ipsa"),
    "politica fiscal": ("fiscal", "budget", "deuda", "hacienda", "treasury"),
    "bancos centrales": (
        "fed", "federal reserve", "reserva federal", "fomc", "federal open market committee", "ecb",
        "banco central", "bancos centrales", "central bank", "monetary", "monetaria",
    ),
    "geopolitica": ("war", "guerra", "geopolit*", "sanction"),
    "regulacion financiera": ("cmf", "sec", "regulation", "regulacion", "banking"),
    "empresas": ("earnings", "resultados", "company", "companies", "empresa"),
}

# Excepciones puntuales a la busqueda por palabra: el IPC de Mexico es un
# indice bursatil, no el IPC chileno.
_KEYWORD_PATTERN_OVERRIDES: dict[str, str] = {
    "ipc": r"(?<![a-z0-9])(?<!mexico )ipc(?! (?:de )?mexico)(?![a-z0-9])",
}


def _keyword_pattern(keyword: str) -> str:
    if keyword in _KEYWORD_PATTERN_OVERRIDES:
        return _KEYWORD_PATTERN_OVERRIDES[keyword]
    if keyword.endswith("*"):
        return rf"(?<![a-z0-9]){re.escape(keyword[:-1])}"
    # Plural opcional: "tasa" -> "tasas", "sanction" -> "sanctions".
    return rf"(?<![a-z0-9]){re.escape(keyword)}(?:s|es)?(?![a-z0-9])"


def _compile_keywords(keywords_by_label: dict[str, tuple[str, ...]]) -> dict[str, re.Pattern[str]]:
    return {
        label: re.compile("|".join(_keyword_pattern(keyword) for keyword in keywords))
        for label, keywords in keywords_by_label.items()
    }


_REGION_PATTERNS = _compile_keywords(REGION_KEYWORDS)
# "US" solo cuenta en mayusculas en el texto original ("US-Iran war", "US CDC"):
# normalizado seria el pronombre "us". "US$" es la moneda, no la region.
_US_UPPERCASE_PATTERN = re.compile(r"(?<![A-Za-z0-9])US(?![A-Za-z0-9$])")
_TOPIC_PATTERNS = _compile_keywords(TOPIC_KEYWORDS)


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


# Medios chilenos: sus notas de negocios rara vez dicen "Chile" ("Dolar abre
# a la baja"), asi que sin otra senal de region se asumen chilenas. La
# seccion Internacional de DF queda fuera.
CHILEAN_NEWS_SOURCES = frozenset({"La Tercera Pulso", "Diario Financiero"})
_FOREIGN_SECTION_MARKERS = ("/internacional/",)


def default_region(source: str, url: str = "") -> str:
    if source in CHILEAN_NEWS_SOURCES and not any(marker in url for marker in _FOREIGN_SECTION_MARKERS):
        return "Chile"
    return "Global"


def classify_region(title: str, summary: str = "", default: str = "Global") -> str:
    """Region por palabras clave; `default` si ninguna calza."""
    raw = f"{title} {summary}"
    text = normalize_text(raw)
    for region, pattern in _REGION_PATTERNS.items():
        if pattern.search(text) or (region == "EE.UU." and _US_UPPERCASE_PATTERN.search(raw)):
            return region
    return default


def classify_topic(title: str, summary: str = "") -> str:
    text = normalize_text(f"{title} {summary}")
    for topic, pattern in _TOPIC_PATTERNS.items():
        if pattern.search(text):
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
                region=classify_region(item.title, item.summary, default_region(item.source, item.url)),
                topic=classify_topic(item.title, item.summary),
            )
        )
    return classified


def filter_recent_news(items: Iterable[NewsItem], hours: int = 18, now: datetime | None = None) -> list[NewsItem]:
    reference = now or datetime.now(UTC)
    since = reference - timedelta(hours=hours)
    return [item for item in items if item.timestamp >= since]
