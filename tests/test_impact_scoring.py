from datetime import UTC, datetime

from services.impact_scoring import calculate_impact_score
from storage.models import MarketSnapshot, NewsItem


def test_calculate_impact_score_high_impact_macro_news() -> None:
    item = NewsItem(
        timestamp=datetime.now(UTC),
        source="Federal Reserve",
        title="Fed signals rates decision as inflation remains elevated",
        url="https://example.com/fed",
        summary="Global markets react to central bank guidance.",
        region="EE.UU.",
        topic="tasas",
    )
    snapshots = [MarketSnapshot(datetime.now(UTC), "SP500", "S&P 500", 5000.0, -1.7, "mock")]

    assert calculate_impact_score(item, snapshots, [item]) >= 8


def test_unrelated_market_move_does_not_inflate_score() -> None:
    item = NewsItem(
        timestamp=datetime.now(UTC),
        source="Federal Reserve",
        title="Fed signals rates decision as inflation remains elevated",
        url="https://example.com/fed",
        summary="Central bank guidance remains in focus.",
        region="EE.UU.",
        topic="tasas",
    )
    snapshots = [MarketSnapshot(datetime.now(UTC), "COPPER", "Cobre", 4.0, 6.0, "mock")]

    assert calculate_impact_score(item, snapshots, [item]) == 7


def test_calculate_impact_score_caps_at_ten() -> None:
    item = NewsItem(
        timestamp=datetime.now(UTC),
        source="Bloomberg",
        title="Chile inflation and copper shock move dollar rates",
        url="https://example.com/chile",
        summary="Central bank and global markets in focus.",
        region="Global",
        topic="bancos centrales",
    )
    snapshots = [MarketSnapshot(datetime.now(UTC), "COPPER", "Cobre", 4.0, 3.0, "mock")]

    assert calculate_impact_score(item, snapshots, [item]) == 9
