"""Deterministic grouping and country inference for phase 2 routing."""

from collections import defaultdict

from services.ai.schemas import AiRoutedNewsInput
from storage.models import NewsItem

COUNTRY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Chile": ("chile", "hacienda", "bcch", "banco central de chile", "cmf", "ipch", "ipsa"),
    "Estados Unidos": ("fed", "federal reserve", "eeuu", "ee.uu.", "u.s.", "united states", "bls", "bea", "treasury"),
    "Eurozona": ("ecb", "eurozona", "euro area", "europe", "europa", "bund"),
    "Brasil": ("brasil", "brazil", "bovespa", "bcb"),
    "Mexico": ("mexico", "banxico", "mexican"),
    "China": ("china", "pboc", "yuan"),
    "Reino Unido": ("uk", "reino unido", "boe", "bank of england"),
    "Japon": ("japon", "japan", "boj"),
}


def infer_country(title: str, summary: str = "", source: str = "") -> str | None:
    """Infer a country from title/summary/source using keyword matching.

    Returns the first matching country, or None if no match.
    """
    text = f"{title} {summary} {source}".lower()
    for country, keywords in COUNTRY_KEYWORDS.items():
        if any(kw in text for kw in keywords):
            return country
    return None


def to_routed_input(item: NewsItem) -> AiRoutedNewsInput:
    """Convert a NewsItem to an AiRoutedNewsInput with country inference."""
    country = infer_country(item.title, item.summary or "", item.source)
    return AiRoutedNewsInput(
        id=item.url,
        timestamp=item.timestamp,
        source=item.source,
        title=item.title,
        url=item.url,
        summary=item.summary or "",
        region=item.region,
        country=country,
        topic=item.topic,
        impact_score=item.impact_score or 0,
    )


def select_and_prepare(
    news_items: list[NewsItem],
    max_news: int = 30,
) -> list[AiRoutedNewsInput]:
    """Sort by impact_score desc, limit, and convert to AiRoutedNewsInput."""
    sorted_news = sorted(
        news_items,
        key=lambda n: n.impact_score or 0,
        reverse=True,
    )
    return [to_routed_input(item) for item in sorted_news[:max_news]]


def group_by_region(items: list[AiRoutedNewsInput]) -> dict[str, list[AiRoutedNewsInput]]:
    """Group routed news by region."""
    groups: dict[str, list[AiRoutedNewsInput]] = defaultdict(list)
    for item in items:
        groups[item.region].append(item)
    return dict(groups)


def group_by_country(items: list[AiRoutedNewsInput]) -> dict[str, list[AiRoutedNewsInput]]:
    """Group routed news by country (falls back to region if country is None)."""
    groups: dict[str, list[AiRoutedNewsInput]] = defaultdict(list)
    for item in items:
        key = item.country or item.region
        groups[key].append(item)
    return dict(groups)


def group_by_topic(items: list[AiRoutedNewsInput]) -> dict[str, list[AiRoutedNewsInput]]:
    """Group routed news by topic."""
    groups: dict[str, list[AiRoutedNewsInput]] = defaultdict(list)
    for item in items:
        groups[item.topic].append(item)
    return dict(groups)


def limit_groups(
    items: list[AiRoutedNewsInput],
    max_per_group: int = 10,
) -> list[AiRoutedNewsInput]:
    """Limit items per group (by topic), keeping highest impact first."""
    by_topic = group_by_topic(items)
    result: list[AiRoutedNewsInput] = []
    for topic_items in by_topic.values():
        sorted_items = sorted(topic_items, key=lambda x: x.impact_score, reverse=True)
        result.extend(sorted_items[:max_per_group])
    return result


def urls_for(items: list[AiRoutedNewsInput]) -> list[str]:
    """Extract URLs from a list of routed news items."""
    return [item.url for item in items]
