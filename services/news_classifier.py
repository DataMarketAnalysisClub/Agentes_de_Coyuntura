import re
import unicodedata
from collections import defaultdict
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
    "Chile": (
        "chile", "chilen*", "chilean", "bcch", "banco central de chile", "cmf", "ipc", "imacec", "hacienda",
        "codelco",
    ),
    # Lideres y empresas estatales: "Lula y Bolsonaro empatan" no nombra al pais.
    "Latam": (
        "latam", "brasil", "brazil*", "mexic*", "colombi*", "peru", "peruan*", "peruvian", "argentin*", "bovespa",
        "lula", "bolsonaro", "milei", "sheinbaum", "petrobras", "pemex",
    ),
    "EE.UU.": (
        "fed", "federal reserve", "reserva federal", "fomc", "federal open market committee", "united states",
        "estados unidos", "eeuu", "ee.uu", "u.s", "wall street", "bls", "bea", "s&p 500", "nasdaq", "dow jones",
        "treasury", "treasuries",
    ),
    "Global": ("global", "world", "europe*", "ecb", "imf", "china", "chinese", "geopolit*", "g7", "g20", "opec", "opep"),
}

# El orden importa solo para desempatar (ver `classify_topic`): los temas
# macro van antes que los de mercado, y FX antes que commodities porque el
# dolar es lo que mas mira el lector chileno.
TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "tasas": ("tasa", "rate", "yield", "treasury", "treasuries"),
    "inflacion": ("ipc", "inflacion", "inflation", "cpi", "ppi"),
    "actividad": ("pib", "gdp", "imacec", "actividad", "growth", "crecimiento", "recesion", "recession"),
    "empleo": (
        "empleo", "desempleo", "desocupacion", "laboral", "jobs", "job", "payroll", "unemployment", "labor",
        "labour", "hiring", "puestos de trabajo", "contratacion",
    ),
    "politica fiscal": (
        "fiscal", "budget", "deuda", "hacienda", "treasury", "presupuesto", "gasto publico", "deficit", "impuesto",
        "tributari*",
    ),
    "FX": ("dolar", "dollar", "fx", "forex", "currency", "currencies", "peso", "divisa", "tipo de cambio"),
    "commodities": (
        "cobre", "copper", "oil", "petroleo", "crudo", "crude", "brent", "wti", "gold", "oro", "litio", "lithium",
        "gas natural", "natural gas", "diesel", "gasolina", "gasoline", "bencina*", "combustible*", "opec",
        "opep", "aramco",
    ),
    "renta variable": ("acciones", "equity", "equities", "stock", "s&p", "nasdaq", "ipsa", "bolsa", "wall street"),
    "bancos centrales": (
        "fed", "federal reserve", "reserva federal", "fomc", "federal open market committee", "ecb",
        "banco central", "bancos centrales", "central bank", "monetary", "monetaria", "boe", "bank of england",
        "boj", "bank of japan", "bank of canada", "rba", "banxico", "copom", "pboc", "snb", "riksbank",
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


def compile_keywords(keywords_by_label: dict[str, tuple[str, ...]]) -> dict[str, re.Pattern[str]]:
    return {
        label: re.compile("|".join(_keyword_pattern(keyword) for keyword in keywords))
        for label, keywords in keywords_by_label.items()
    }


_REGION_PATTERNS = compile_keywords(REGION_KEYWORDS)
# "US" solo cuenta en mayusculas en el texto original ("US-Iran war", "US CDC"):
# normalizado seria el pronombre "us". "US$" es la moneda, no la region.
_US_UPPERCASE_PATTERN = re.compile(r"(?<![A-Za-z0-9])US(?![A-Za-z0-9$])")
_TOPIC_PATTERNS = compile_keywords(TOPIC_KEYWORDS)

# El titular dice de que trata la nota; el resumen solo la complementa.
TOPIC_TITLE_WEIGHT = 3.0
TOPIC_SUMMARY_WEIGHT = 1.0

# Frases con una palabra clave de un tema que pertenecen a otro: "tasa de
# desocupacion" es empleo y "tasa de inflacion" es inflacion, no "tasas".
TOPIC_MASKED_PHRASES: dict[str, tuple[str, ...]] = {
    "tasas": (
        "tasa de desempleo", "tasa de desocupacion", "tasa de empleo", "tasa de inflacion", "unemployment rate",
        "jobless rate", "inflation rate", "treasury department", "treasury secretary", "departamento del tesoro",
    ),
    # "Fiscal" tambien es quien acusa en un juicio y el adjetivo de bienes del
    # Estado ("terreno fiscal"); "fiscal year" es el ano contable de una empresa.
    "politica fiscal": (
        "el fiscal", "la fiscal", "los fiscales", "fiscal nacional", "fiscal regional", "terreno fiscal",
        "terrenos fiscales", "fiscal year", "fiscal quarter",
    ),
}
_TOPIC_MASKED_PATTERNS = {
    topic: re.compile("|".join(re.escape(phrase) for phrase in phrases))
    for topic, phrases in TOPIC_MASKED_PHRASES.items()
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
    """Tema con mas menciones, ponderando el titulo sobre el resumen.

    Antes ganaba el primer tema con alguna mencion, y como "tasas" va primero,
    "la tasa de desocupacion" en el resumen volvia "tasas" una nota laboral.
    Los empates se resuelven por el orden de `TOPIC_KEYWORDS`.
    """
    title_text = normalize_text(title)
    summary_text = normalize_text(summary)
    best_topic, best_score = "macro general", 0.0
    for topic, pattern in _TOPIC_PATTERNS.items():
        masked = _TOPIC_MASKED_PATTERNS.get(topic)
        title_hits = len(pattern.findall(masked.sub(" ", title_text) if masked else title_text))
        summary_hits = len(pattern.findall(masked.sub(" ", summary_text) if masked else summary_text))
        score = TOPIC_TITLE_WEIGHT * title_hits + TOPIC_SUMMARY_WEIGHT * summary_hits
        if score > best_score:
            best_topic, best_score = topic, score
    return best_topic


@lru_cache(maxsize=4096)
def _similarity_ratio(left: str, right: str) -> float:
    return SequenceMatcher(None, normalize_text(left), normalize_text(right)).ratio()


def is_similar_title(left: str, right: str, threshold: float = 0.88) -> bool:
    return _similarity_ratio(normalize_title(left), normalize_title(right)) >= threshold


# Palabras que no distinguen una historia de otra.
_STOPWORDS = frozenset(
    "the a an and or of to in on at for by with from as is are was be its it this that after amid over into"
    " says say said new de la el los las y o en por con para del al se su sus que un una tras ante sobre mas"
    .split()
)
STORY_SIMILARITY_THRESHOLD = 0.5


@lru_cache(maxsize=4096)
def title_tokens(title: str) -> frozenset[str]:
    """Palabras significativas del titulo (sin stopwords ni palabras de 1-2 letras)."""
    return frozenset(
        token for token in normalize_title(title).split() if len(token) > 2 and token not in _STOPWORDS
    )


def is_same_story(left: str, right: str) -> bool:
    """Dos medios contando la misma historia con otras palabras.

    `is_similar_title` exige casi el mismo texto (sirve para duplicados); aqui
    basta compartir la mitad de las palabras significativas ("Fed's Barr says
    more rate hikes likely" / "Fed's Barr signals more rate hikes needed").
    """
    left_tokens, right_tokens = title_tokens(left), title_tokens(right)
    shared = left_tokens & right_tokens
    # Sin palabras en comun no hay historia comun: evita el SequenceMatcher.
    if left_tokens and right_tokens and not shared:
        return False
    if len(left_tokens) >= 3 and len(right_tokens) >= 3:
        if len(shared) / len(left_tokens | right_tokens) >= STORY_SIMILARITY_THRESHOLD:
            return True
    return is_similar_title(left, right)


def deduplicate_news(items: Iterable[RawNewsItem]) -> list[RawNewsItem]:
    seen_urls: set[str] = set()
    unique: list[RawNewsItem] = []
    # Indice palabra -> notas ya aceptadas: cada titulo se compara solo con
    # los que comparten alguna palabra, no con todos (antes O(n^2) completo).
    by_token: dict[str, list[RawNewsItem]] = defaultdict(list)
    short_titles: list[RawNewsItem] = []
    for item in items:
        canonical_url = canonicalize_url(item.url)
        if canonical_url in seen_urls:
            continue
        tokens = title_tokens(item.title)
        if tokens:
            candidates = {id(existing): existing for token in tokens for existing in by_token[token]}
            candidates.update({id(existing): existing for existing in short_titles})
            to_compare = candidates.values()
        else:
            to_compare = unique
        if any(is_similar_title(item.title, existing.title, threshold=0.84) for existing in to_compare):
            continue
        seen_urls.add(canonical_url)
        if tokens:
            for token in tokens:
                by_token[token].append(item)
        else:
            short_titles.append(item)
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
