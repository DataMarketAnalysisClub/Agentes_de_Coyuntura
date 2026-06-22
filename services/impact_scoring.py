from collections.abc import Iterable

from services.news_classifier import is_similar_title, normalize_text
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


def count_similar_headlines(target: NewsItem, items: Iterable[NewsItem]) -> int:
    return sum(
        1
        for item in items
        if item.url != target.url and (is_similar_title(target.title, item.title) or target.topic == item.topic)
    )


def calculate_impact_score(
    item: NewsItem,
    snapshots: Iterable[MarketSnapshot] | None = None,
    all_news: Iterable[NewsItem] | None = None,
) -> int:
    score = 0
    source = normalize_text(item.source)
    text = normalize_text(f"{item.title} {item.summary} {item.topic} {item.region}")

    if any(source_name in source for source_name in RECOGNIZED_SOURCES):
        score += 2
    if any(keyword in text for keyword in HIGH_IMPACT_KEYWORDS):
        score += 2
    if snapshots:
        score += score_asset_movements(snapshots)
    if item.topic in MACRO_TOPICS or "central" in text:
        score += 2
    if item.region in {"Latam", "EE.UU.", "Global"}:
        score += 1
    if all_news and count_similar_headlines(item, all_news) > 0:
        score += 1

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
