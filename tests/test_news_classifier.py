from datetime import UTC, datetime

from data_sources.rss_news_client import RawNewsItem
from services.news_classifier import canonicalize_url, deduplicate_news


def test_canonicalize_url_strips_tracking_params() -> None:
    url = "https://Example.com/story/?utm_source=x&keep=1&fbclid=abc#section"

    assert canonicalize_url(url) == "https://example.com/story?keep=1"


def test_deduplicate_news_uses_canonical_url_and_similar_titles() -> None:
    now = datetime.now(UTC)
    items = [
        RawNewsItem(now, "A", "Fed signals rate decision", "https://example.com/a?utm_source=x", ""),
        RawNewsItem(now, "B", "Fed signals rate decision", "https://example.com/a?utm_medium=y", ""),
        RawNewsItem(now, "C", "Fed signals rates decision", "https://example.com/b", ""),
    ]

    unique = deduplicate_news(items)

    assert len(unique) == 1
    assert unique[0].url == "https://example.com/a"
