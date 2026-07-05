from dataclasses import dataclass

from services.news_classifier import normalize_text
from storage.models import NewsItem

SOURCE_TIERS = {
    "federal reserve": 1,
    "ecb": 1,
    "banco central": 1,
    "cmf": 1,
    "ine": 1,
    "financial times": 2,
    "reuters": 2,
    "bloomberg": 2,
    "la tercera pulso": 2,
    "marketwatch": 3,
    "investing.com": 3,
}

LOW_VALUE_PATTERNS = (
    "social security",
    "retirement",
    "retiree",
    "pension advice",
    "high earners",
    "better time to invest",
    "how much should i",
    "personal finance",
    "mortgage",
    "credit card",
    "dividend yield dwarfs",
    "value stocks",
    "top newsletters",
    "newsletters are betting",
    "13 stocks",
    "stock picks",
    "hodl",
    "bitcoin",
    "crypto",
    "buy its stock",
    "motley fool",
    "the street",
    "seeking alpha",
)

HIGH_SIGNAL_TERMS = (
    "fed",
    "federal reserve",
    "ecb",
    "inflation",
    "inflacion",
    "rates",
    "tasas",
    "yield",
    "treasury",
    "jobs",
    "payroll",
    "cpi",
    "pce",
    "gdp",
    "imacec",
    "copper",
    "cobre",
    "oil",
    "brent",
    "wti",
    "dollar",
    "dolar",
    "peso",
    "china",
    "wall street",
    "nasdaq",
    "s&p",
    "geopolit",
    "central bank",
    "banco central",
    "tariff",
    "tariffs",
    "trade",
    "shipping costs",
    "supreme court",
    "fed governor",
)


@dataclass(frozen=True)
class NewsQualityDecision:
    keep: bool
    reason: str
    score: int


def evaluate_news_quality(item: NewsItem) -> NewsQualityDecision:
    source = normalize_text(item.source)
    text = normalize_text(f"{item.title} {item.summary} {item.topic} {item.region} {item.source}")

    if any(pattern in text for pattern in LOW_VALUE_PATTERNS):
        return NewsQualityDecision(False, "low_value_pattern", 0)

    tier = source_tier(source)
    score = max(0, 5 - tier)
    has_high_signal = any(term in text for term in HIGH_SIGNAL_TERMS)
    if has_high_signal:
        score += 3
    elif tier > 1:
        return NewsQualityDecision(False, "low_macro_relevance", score)
    if item.region in {"Chile", "Latam", "EE.UU."}:
        score += 1
    if item.impact_score >= 7:
        score += 2
    elif item.impact_score >= 5:
        score += 1

    if score < 4:
        return NewsQualityDecision(False, "low_editorial_score", score)
    return NewsQualityDecision(True, "selected_candidate", score)


def source_tier(normalized_source: str) -> int:
    for source_name, tier in SOURCE_TIERS.items():
        if source_name in normalized_source:
            return tier
    return 4
