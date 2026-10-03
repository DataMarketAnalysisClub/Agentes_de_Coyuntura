from datetime import UTC, datetime

from services.impact_scoring import calculate_impact_score, count_covering_sources
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


def _story(source: str, title: str, url: str) -> NewsItem:
    return NewsItem(datetime.now(UTC), source, title, url, "", "Global", "macro general")


def test_coverage_counts_other_sources_with_the_same_story_not_the_same_topic() -> None:
    target = _story("Investing.com", "Fed’s Barr says more rate hikes likely to be needed to curb inflation", "u1")
    same_source = _story("Investing.com", "Fed’s Barr signals more rate hikes needed amid inflation risks", "u2")
    other_source = _story("Financial Times", "Fed’s Barr says more rate hikes may be needed to curb inflation", "u3")
    third_source = _story("MarketWatch", "Barr says more Fed rate hikes likely needed to curb inflation", "u4")
    unrelated = _story("Reuters", "Oil prices steady as traders weigh supply outlook", "u5")

    assert count_covering_sources(target, [target, same_source, unrelated]) == 0
    assert count_covering_sources(target, [target, other_source]) == 1
    assert count_covering_sources(target, [target, other_source, third_source, unrelated]) == 2

    alone = calculate_impact_score(target, None, [target, unrelated])
    covered = calculate_impact_score(target, None, [target, other_source, third_source])
    assert covered - alone == 2


def test_source_and_keywords_match_whole_words() -> None:
    item = NewsItem(
        datetime.now(UTC), "Online Trading Blog", "FedEx fintech unit expands", "u", "", "Chile", "empresas"
    )

    # Solo la region "Chile" (palabra clave) suma; ni "ine" en "online" ni "fed" en "FedEx".
    assert calculate_impact_score(item) == 2


def test_treasury_department_is_not_the_bond_market() -> None:
    snapshots = [MarketSnapshot(datetime.now(UTC), "US10Y", "Treasury 10Y", 5.28, 0.4, "mock")]
    department = NewsItem(
        datetime.now(UTC), "MarketWatch", "The Treasury Department started Trump accounts for 60 million kids",
        "u1", "", "EE.UU.", "politica fiscal",
    )
    bonds = NewsItem(
        datetime.now(UTC), "MarketWatch", "Treasury yields climb to a two-decade high", "u2", "", "EE.UU.", "tasas"
    )

    assert calculate_impact_score(department, snapshots) == calculate_impact_score(department)
    assert calculate_impact_score(bonds, snapshots) > calculate_impact_score(bonds)
