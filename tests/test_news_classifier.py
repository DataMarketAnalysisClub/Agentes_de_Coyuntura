from datetime import UTC, datetime

import pytest

from data_sources.rss_news_client import RawNewsItem
from services.news_classifier import (
    canonicalize_url,
    classify_region,
    classify_topic,
    deduplicate_news,
)


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


@pytest.mark.parametrize(
    ("title", "not_expected"),
    [
        ("Investors focus on status of talks", "EE.UU."),  # "us " dentro de focus/status
        ("Energy sector rallies", "regulacion financiera"),  # "sec" dentro de sector
        ("Markets in turmoil after vote", "commodities"),  # "oil" dentro de turmoil
        ("Corporate bond issuance slows", "tasas"),  # "rate" dentro de corporate
        ("Tell us what you think about bonus season", "EE.UU."),  # pronombre "us"
        ("EFE cifra en US$ 800 millones los pagos", "EE.UU."),  # US$ es moneda
    ],
)
def test_classifier_ignores_substring_false_positives(title: str, not_expected: str) -> None:
    assert classify_region(title) != not_expected
    assert classify_topic(title) != not_expected


def test_mexico_ipc_index_is_not_chilean_inflation() -> None:
    assert classify_region("IPC de Mexico sube 1% por bancos") == "Latam"
    assert classify_region("Bolsa: el Mexico IPC cierra al alza") == "Latam"
    assert classify_region("IPC de agosto sube 0,3%") == "Chile"


@pytest.mark.parametrize(
    ("title", "region", "topic"),
    [
        ("Fed signals two more rate cuts", "EE.UU.", "tasas"),
        ("Las tasas largas suben en Chile", "Chile", "tasas"),
        ("U.S. yields climb as jobs data beats", "EE.UU.", "tasas"),
        ("Tasa de desempleo en EE.UU. baja", "EE.UU.", "tasas"),
        ("Desempleo en Chile llega a 8,7%", "Chile", "empleo"),
        ("Oil jumps on new sanctions", "Global", "commodities"),
        ("Chilean peso weakens", "Chile", "FX"),
        ("Tensiones geopoliticas en Europa", "Global", "geopolitica"),
        ("Brazil's central bank holds", "Latam", "bancos centrales"),
        ("Federal Reserve issues FOMC statement", "EE.UU.", "bancos centrales"),
        ("US-Iran war adds costs to EU fuel bill", "EE.UU.", "geopolitica"),
        ("Plan laboral del gobierno avanza", "Global", "empleo"),
    ],
)
def test_classifier_matches_whole_words_and_plurals(title: str, region: str, topic: str) -> None:
    assert classify_region(title) == region
    assert classify_topic(title) == topic
