from datetime import UTC, datetime, timedelta

from services.news_selection import select_brief_news, select_executive_news
from storage.models import NewsItem


def _news(title: str, url: str, timestamp: datetime, source: str = "A", score: int = 8) -> NewsItem:
    return NewsItem(
        timestamp=timestamp,
        source=source,
        title=title,
        url=url,
        summary="",
        region="Global",
        topic="tasas",
        impact_score=score,
    )


def test_select_brief_news_skips_previously_mentioned_story() -> None:
    now = datetime.now(UTC)
    previous = _news("Fed signals rate decision", "https://example.com/fed", now - timedelta(hours=2))
    current = _news("Fed signals rate decision", "https://example.com/fed?utm_source=x", now)

    selected = select_brief_news([current], mentioned_news=[previous])

    assert selected == []


def test_select_brief_news_allows_explicit_update() -> None:
    now = datetime.now(UTC)
    previous = _news("Fed signals rate decision", "https://example.com/fed", now - timedelta(hours=2))
    current = _news("Actualiza: Fed signals rate decision", "https://example.com/fed", now)

    selected = select_brief_news([current], mentioned_news=[previous])

    assert selected == [current]


def test_select_brief_news_caps_source_and_topic() -> None:
    now = datetime.now(UTC)
    items = [
        _news("A", "https://example.com/a", now, source="Same", score=10),
        _news("B", "https://example.com/b", now, source="Same", score=9),
        _news("C", "https://example.com/c", now, source="Same", score=8),
    ]

    selected = select_brief_news(items, per_source_limit=2, per_topic_limit=3)

    assert [item.title for item in selected] == ["A", "B"]


def test_select_executive_news_filters_low_value_personal_finance() -> None:
    now = datetime.now(UTC)
    items = [
        _news(
            "Does delaying Social Security make sense for high earners like me?",
            "https://example.com/social-security",
            now,
            source="MarketWatch",
            score=9,
        ),
        _news(
            "Fed signals rates decision as inflation remains elevated",
            "https://example.com/fed",
            now,
            source="Federal Reserve",
            score=8,
        ),
    ]

    result = select_executive_news(items)

    assert [item.title for item in result.selected] == ["Fed signals rates decision as inflation remains elevated"]
    assert result.rejected_quality == 1


def test_select_executive_news_limits_to_three() -> None:
    now = datetime.now(UTC)
    items = [
        _news(f"Fed inflation rates signal {idx}", f"https://example.com/{idx}", now, source=f"Source {idx}", score=8)
        for idx in range(5)
    ]

    result = select_executive_news(items, per_topic_limit=5)

    assert len(result.selected) == 3


def test_select_executive_news_requires_macro_signal_for_non_official_sources() -> None:
    now = datetime.now(UTC)
    items = [
        NewsItem(
            timestamp=now,
            source="La Tercera Pulso",
            title="Gremio de laboratorios destaca potencial exportador de medicamentos",
            url="https://example.com/labs",
            summary="",
            region="Chile",
            topic="empresas",
            impact_score=8,
        ),
        _news(
            "Tariffs and shipping costs pressure global markets",
            "https://example.com/trade",
            now,
            source="Financial Times",
            score=7,
        ),
    ]

    result = select_executive_news(items)

    assert [item.title for item in result.selected] == ["Tariffs and shipping costs pressure global markets"]
    assert result.rejected_quality == 1


def test_select_executive_news_filters_crypto_single_stock_noise() -> None:
    now = datetime.now(UTC)
    items = [
        _news(
            "Bye-bye, HODL: Strategy plans to sell bitcoin and buy its stock",
            "https://example.com/crypto",
            now,
            source="MarketWatch",
            score=8,
        ),
        _news(
            "ECB says rates remain data dependent as inflation cools",
            "https://example.com/ecb",
            now,
            source="ECB",
            score=8,
        ),
    ]

    result = select_executive_news(items)

    assert [item.title for item in result.selected] == ["ECB says rates remain data dependent as inflation cools"]
    assert result.rejected_quality == 1
