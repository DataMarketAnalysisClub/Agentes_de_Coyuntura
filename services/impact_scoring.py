import re
from collections.abc import Iterable

from services.news_classifier import compile_keywords, is_same_story, normalize_text
from storage.models import MarketSnapshot, NewsItem

RECOGNIZED_SOURCES = (
    "banco central",
    "cmf",
    "ine",
    "hacienda",
    "federal reserve",
    "bls",
    "bea",
    "ecb",
    "imf",
    "world bank",
    "reuters",
    "bloomberg",
    "financial times",
    "diario financiero",
)

HIGH_IMPACT_KEYWORDS = (
    "chile",
    "bcch",
    "fed",
    "ipc",
    "inflacion",
    "inflation",
    "empleo",
    "jobs",
    "tasas",
    "rates",
    "cobre",
    "copper",
    "dolar",
    "dollar",
)

MACRO_TOPICS = {"tasas", "inflacion", "actividad", "empleo", "politica fiscal", "bancos centrales"}

MOVEMENT_THRESHOLDS = {
    "USDCLP": 1.2,
    "COPPER": 2.0,
    "GOLD": 1.5,
    "SP500": 1.5,
    "VOO": 1.5,
    "NASDAQ100": 2.0,
    "IPSA": 1.5,
    "US10Y": 10.0,
    "DXY": 0.8,
}

ASSET_TEXT_KEYWORDS = {
    "USDCLP": ("usdclp", "usd clp", "dolar", "dollar", "peso", "fx", "currency"),
    "COPPER": ("cobre", "copper", "commodity", "commodities"),
    "GOLD": ("oro", "gold", "commodity", "commodities"),
    "SP500": ("s&p", "sp500", "s p 500", "wall street", "stocks", "equity", "markets", "mercados"),
    "VOO": ("s&p", "sp500", "s p 500", "wall street", "stocks", "equity", "markets", "mercados"),
    "NASDAQ100": ("nasdaq", "tech", "tecnologia", "stocks", "equity", "markets", "mercados"),
    "IPSA": ("ipsa", "acciones chilenas", "bolsa chilena", "stocks", "equity", "mercados"),
    "US10Y": ("treasury", "yield", "tasas", "rates", "bonos", "bonds"),
    "DXY": ("dxy", "dolar", "dollar", "fx", "currency"),
}


# Palabras completas (antes substrings: "fed" calzaba con "fedex", "tech" con
# "fintech", "ine" con "online").
_RECOGNIZED_SOURCE_PATTERN = compile_keywords({"source": RECOGNIZED_SOURCES})["source"]
_HIGH_IMPACT_PATTERN = compile_keywords({"impact": HIGH_IMPACT_KEYWORDS})["impact"]
_ASSET_TEXT_PATTERNS = compile_keywords(ASSET_TEXT_KEYWORDS)
_CENTRAL_PATTERN = compile_keywords({"central": ("central",)})["central"]
# "Treasury" como institucion, no como bonos: "The Treasury Department started
# Trump accounts for kids" no tiene que ver con el Treasury 10Y.
_NOT_BOND_PHRASES = re.compile(r"treasury department|treasury secretary|departamento del tesoro")


def score_asset_movements(snapshots: Iterable[MarketSnapshot]) -> int:
    total = 0
    for snapshot in snapshots:
        if snapshot.change_pct is None:
            continue
        threshold = MOVEMENT_THRESHOLDS.get(snapshot.symbol)
        if threshold is None:
            continue
        observed = abs(snapshot.change_pct)
        if snapshot.symbol == "US10Y":
            observed = abs(snapshot.change_pct * 100)

        ratio = observed / threshold
        if ratio >= 3:
            total += 4
        elif ratio >= 2:
            total += 3
        elif ratio >= 1.5:
            total += 2
        elif ratio >= 1:
            total += 1

    return min(total, 6)


def score_related_asset_movements(snapshots: Iterable[MarketSnapshot], text: str) -> int:
    text = _NOT_BOND_PHRASES.sub(" ", text)
    related = [
        snapshot
        for snapshot in snapshots
        if snapshot.symbol in _ASSET_TEXT_PATTERNS and _ASSET_TEXT_PATTERNS[snapshot.symbol].search(text)
    ]
    return score_asset_movements(related)


def count_covering_sources(target: NewsItem, items: Iterable[NewsItem]) -> int:
    """Cuantas otras fuentes publican la misma historia.

    Reemplaza a `count_similar_headlines`, que contaba como "similar" cualquier
    nota del mismo tema: 159 de 160 notas reales sumaban +1, sin informacion.
    """
    return len(
        {
            item.source
            for item in items
            if item.source != target.source and item.url != target.url and is_same_story(target.title, item.title)
        }
    )


def calculate_impact_score(
    item: NewsItem,
    snapshots: Iterable[MarketSnapshot] | None = None,
    all_news: Iterable[NewsItem] | None = None,
) -> int:
    score = 0
    source = normalize_text(item.source)
    text = normalize_text(f"{item.title} {item.summary} {item.topic} {item.region}")

    if _RECOGNIZED_SOURCE_PATTERN.search(source):
        score += 2
    # El texto incluye la region: una nota de region "Chile" suma por la
    # palabra clave "chile" aunque no la nombre (por eso Chile no esta en el
    # +1 por region de abajo).
    if _HIGH_IMPACT_PATTERN.search(text):
        score += 2
    if snapshots:
        score += score_related_asset_movements(snapshots, text)
    if item.topic in MACRO_TOPICS or _CENTRAL_PATTERN.search(text):
        score += 2
    if item.region in {"Latam", "EE.UU.", "Global"}:
        score += 1
    if all_news:
        # Una historia que cubren varios medios pesa mas que una exclusiva.
        score += min(count_covering_sources(item, all_news), 2)

    return min(score, 10)


def with_impact_scores(items: list[NewsItem], snapshots: Iterable[MarketSnapshot]) -> list[NewsItem]:
    return [
        NewsItem(
            timestamp=item.timestamp,
            source=item.source,
            title=item.title,
            url=item.url,
            summary=item.summary,
            region=item.region,
            topic=item.topic,
            impact_score=calculate_impact_score(item, snapshots, items),
        )
        for item in items
    ]
