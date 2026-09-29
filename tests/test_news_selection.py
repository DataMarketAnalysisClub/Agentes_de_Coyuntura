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


def _chile(title: str, url: str, now: datetime, source: str = "La Tercera Pulso", score: int = 5) -> NewsItem:
    return NewsItem(now, source, title, url, "", "Chile", "FX", score)


def test_guaranteed_chile_slot_replaces_lowest_ranked_headline() -> None:
    now = datetime.now(UTC)
    global_items = [
        _news(f"Fed inflation rates signal {idx}", f"https://example.com/{idx}", now, source=source, score=9)
        for idx, source in enumerate(["ECB", "Financial Times", "Reuters"])
    ]
    chile = _chile("Dolar cae y el peso se aprecia", "https://example.com/cl", now, score=0)

    # Sin cupo, la nota chilena queda fuera por puntaje.
    assert chile not in select_executive_news([*global_items, chile], per_topic_limit=5, guaranteed_region=None).selected
    result = select_executive_news([*global_items, chile], per_topic_limit=5)

    assert [item.title for item in result.selected] == [
        "Fed inflation rates signal 0",
        "Fed inflation rates signal 1",
        "Dolar cae y el peso se aprecia",
    ]


def test_guaranteed_chile_slot_not_forced_when_no_chilean_news_passes_quality() -> None:
    now = datetime.now(UTC)
    items = [
        _news(f"Fed inflation rates signal {idx}", f"https://example.com/{idx}", now, source=f"Source {idx}")
        for idx in range(3)
    ]
    low_quality = _chile("Gremio de laboratorios destaca potencial exportador", "https://example.com/labs", now)

    result = select_executive_news([*items, low_quality], per_topic_limit=5)

    assert all(item.region == "Global" for item in result.selected)
    assert len(result.selected) == 3


def test_guaranteed_chile_slot_respects_source_cap_and_can_be_disabled() -> None:
    now = datetime.now(UTC)
    items = [
        _news("ECB inflation rates signal", "https://example.com/b", now, source="ECB", score=9),
        _news("Fed inflation rates signal", "https://example.com/a", now, source="La Tercera Pulso", score=9),
        _news("Oil and dollar rally", "https://example.com/c", now, source="Financial Times", score=9),
        _chile("Dolar cae en Chile", "https://example.com/cl1", now, source="La Tercera Pulso", score=0),
        _chile("Cobre sube por huelga", "https://example.com/cl2", now, source="Diario Financiero", score=0),
    ]

    result = select_executive_news(items, per_topic_limit=5)
    # La Tercera ya ocupa su cupo de fuente: entra la nota de DF.
    assert result.selected[-1].title == "Cobre sube por huelga"
    assert "Cobre sube por huelga" not in [
        item.title for item in select_executive_news(items, per_topic_limit=5, guaranteed_region=None).selected
    ]


def test_administrative_central_bank_notices_are_filtered() -> None:
    now = datetime.now(UTC)
    items = [
        _news("Federal Reserve Board announces approval of application by Peoples Bancorp", "https://x/1", now, source="Federal Reserve"),
        _news("Federal Reserve Board issues enforcement action with former employee", "https://x/2", now, source="Federal Reserve"),
        _news("Almost ten million people took part in ECB survey on new euro banknotes", "https://x/3", now, source="ECB"),
        _news("Federal Reserve issues FOMC statement", "https://x/4", now, source="Federal Reserve"),
        # Mismo patron fuera de un banco central: sigue compitiendo.
        _news("SEC enforcement action hits big bank as rates rise", "https://x/5", now, source="Financial Times"),
    ]

    result = select_executive_news(items, per_source_limit=3, per_topic_limit=5)

    assert [item.title for item in result.selected] == [
        "Federal Reserve issues FOMC statement",
        "SEC enforcement action hits big bank as rates rise",
    ]
    assert result.rejected_quality == 3


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
