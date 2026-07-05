from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from services.news_classifier import canonicalize_url, is_similar_title, normalize_text
from services.news_quality import evaluate_news_quality, source_tier
from storage.models import NewsItem

UPDATE_MARKERS = (
    "actualiza",
    "actualizacion",
    "ultima hora",
    "ultimo minuto",
    "nuevo",
    "nueva",
    "update",
    "updated",
    "breaking",
    "revised",
    "revision",
)


@dataclass(frozen=True)
class NewsSelectionResult:
    selected: list[NewsItem]
    total_candidates: int
    rejected_repeated: int
    rejected_quality: int
    rejected_caps: int


def select_brief_news(
    news: Iterable[NewsItem],
    mentioned_news: Iterable[NewsItem] = (),
    limit: int = 5,
    per_source_limit: int = 2,
    per_topic_limit: int = 2,
) -> list[NewsItem]:
    selected: list[NewsItem] = []
    source_counts: dict[str, int] = defaultdict(int)
    topic_counts: dict[str, int] = defaultdict(int)
    mentioned = list(mentioned_news)

    candidates = sorted(news, key=lambda item: (item.impact_score, item.timestamp), reverse=True)
    for item in candidates:
        if _was_already_mentioned(item, mentioned):
            continue
        source_key = normalize_text(item.source)
        topic_key = normalize_text(item.topic)
        if source_counts[source_key] >= per_source_limit:
            continue
        if topic_counts[topic_key] >= per_topic_limit:
            continue

        selected.append(item)
        source_counts[source_key] += 1
        topic_counts[topic_key] += 1
        if len(selected) >= limit:
            break

    return selected


def select_executive_news(
    news: Iterable[NewsItem],
    mentioned_news: Iterable[NewsItem] = (),
    limit: int = 3,
    per_source_limit: int = 1,
    per_topic_limit: int = 2,
) -> NewsSelectionResult:
    selected: list[NewsItem] = []
    source_counts: dict[str, int] = defaultdict(int)
    topic_counts: dict[str, int] = defaultdict(int)
    mentioned = list(mentioned_news)
    candidates = list(news)
    rejected_repeated = 0
    rejected_quality = 0
    rejected_caps = 0

    ordered = sorted(candidates, key=_executive_sort_key, reverse=True)
    for item in ordered:
        if _was_already_mentioned(item, mentioned):
            rejected_repeated += 1
            continue

        quality = evaluate_news_quality(item)
        if not quality.keep:
            rejected_quality += 1
            continue

        source_key = normalize_text(item.source)
        topic_key = normalize_text(item.topic)
        if source_counts[source_key] >= per_source_limit or topic_counts[topic_key] >= per_topic_limit:
            rejected_caps += 1
            continue

        selected.append(item)
        source_counts[source_key] += 1
        topic_counts[topic_key] += 1
        if len(selected) >= limit:
            break

    return NewsSelectionResult(
        selected=selected,
        total_candidates=len(candidates),
        rejected_repeated=rejected_repeated,
        rejected_quality=rejected_quality,
        rejected_caps=rejected_caps,
    )


def _executive_sort_key(item: NewsItem) -> tuple[int, int, int, object]:
    quality = evaluate_news_quality(item)
    tier_bonus = max(0, 5 - source_tier(normalize_text(item.source)))
    return (quality.score, item.impact_score, tier_bonus, item.timestamp)


def _was_already_mentioned(item: NewsItem, mentioned_news: list[NewsItem]) -> bool:
    item_url = canonicalize_url(item.url)
    for previous in mentioned_news:
        same_url = item_url and item_url == canonicalize_url(previous.url)
        same_title = is_similar_title(item.title, previous.title, threshold=0.84)
        if not same_url and not same_title:
            continue
        if _looks_like_update(item, previous):
            continue
        return True
    return False


def _looks_like_update(item: NewsItem, previous: NewsItem) -> bool:
    if item.timestamp <= previous.timestamp:
        return False
    text = normalize_text(f"{item.title} {item.summary}")
    if any(marker in text for marker in UPDATE_MARKERS):
        return True
    return False
