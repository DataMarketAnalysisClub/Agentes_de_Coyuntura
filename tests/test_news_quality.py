from datetime import UTC, datetime

import pytest

from services.news_classifier import classify_region, classify_topic, default_region
from services.news_quality import evaluate_news_quality
from storage.models import NewsItem


def _item(source: str, title: str, summary: str = "", url: str = "https://example.com/n") -> NewsItem:
    # Region y tema como en el pipeline real (`classify_news`).
    region = classify_region(title, summary, default_region(source, url))
    return NewsItem(datetime.now(UTC), source, title, url, summary, region, classify_topic(title, summary), 4)


# Notas reales (2026-09-28/29 y 2026-10-03) que pasaban el filtro.
@pytest.mark.parametrize(
    ("source", "title"),
    [
        ("MarketWatch", "‘I have a low interest rate’: I’m 80 years old. Should I move out of my house?"),
        ("MarketWatch", "‘I want to make her proud’: My mother, a divorcée, died and I’m her executor."),
        ("Investing.com", "S&P 500 wedged at 7,739 between key support and resistance: Live"),
        ("Investing.com", "Dollar Index battles 101.49 double top resistance: Live levels"),
        ("Investing.com", "Bitcoin stuck at $84,947 in tightening range: Live levels"),
        ("Investing.com", "Copart stock hits 52-week low at 26.8 USD"),
        ("Investing.com", "Why is Aritzia stock gaining today?"),
        ("Investing.com", "Cryptocurrency funds see record inflows"),
    ],
)
def test_personal_finance_and_intraday_technical_notes_are_low_value(source: str, title: str) -> None:
    assert evaluate_news_quality(_item(source, title)).reason == "low_value_pattern"


# Notas chilenas reales que se rechazaban por "baja relevancia macro".
@pytest.mark.parametrize(
    ("source", "title", "summary"),
    [
        (
            "La Tercera Pulso",
            "Gobierno anuncia plan laboral que movilizará recursos por unos US$1.350 millones que apunta a crear"
            " más de 100 mil empleos",
            "El plan incluye subsidios a la contratación y empleo directo.",
        ),
        (
            "Diario Financiero",
            "Lula y Flávio Bolsonaro empatan en las encuestas a días de la primera vuelta presidencial",
            "La contienda entra a su etapa decisiva.",
        ),
    ],
)
def test_spanish_macro_news_passes_quality(source: str, title: str, summary: str) -> None:
    assert evaluate_news_quality(_item(source, title, summary)).keep


def test_signal_terms_match_whole_words_only() -> None:
    # "fed" dentro de "FedEx" y "oil" dentro de "turmoil" no son senal macro.
    decision = evaluate_news_quality(_item("MarketWatch", "FedEx shares in turmoil after guidance cut"))

    assert decision.reason == "low_macro_relevance"


# Notas reales del 2026-10-03: las fuentes oficiales pasaban siempre el filtro.
@pytest.mark.parametrize(
    ("source", "title"),
    [
        ("ECB", "Christine Lagarde: Where AI risks meet"),
        ("ECB", "Boris Vujčić: Resilience, integration and competitiveness: building the future of European banking"),
        ("Federal Reserve", "Federal Reserve Board announces new members of community advisory council"),
    ],
)
def test_official_sources_need_a_signal_beyond_their_own_name(source: str, title: str) -> None:
    assert evaluate_news_quality(_item(source, title)).reason == "low_macro_relevance"


@pytest.mark.parametrize(
    ("source", "title"),
    [
        ("ECB", "Decisions taken by the Governing Council of the ECB (in addition to decisions setting interest rates)"),
        (
            "Federal Reserve",
            "Federal Reserve Board announces it will extend, until November 4, the comment period on its proposal",
        ),
    ],
)
def test_recurring_central_bank_paperwork_is_administrative(source: str, title: str) -> None:
    assert evaluate_news_quality(_item(source, title)).reason == "administrative_notice"


@pytest.mark.parametrize(
    ("source", "title"),
    [
        ("Federal Reserve", "Federal Reserve issues FOMC statement"),
        ("ECB", "Monetary policy decisions"),
        ("ECB", "Isabel Schnabel: Inflation outlook and the path for interest rates"),
    ],
)
def test_official_monetary_policy_news_still_passes(source: str, title: str) -> None:
    assert evaluate_news_quality(_item(source, title)).keep


def test_first_person_pattern_does_not_hit_macro_headlines() -> None:
    decision = evaluate_news_quality(_item("MarketWatch", "Fed should increase rates, says former governor"))

    assert decision.keep


# Notas de carrera de MarketWatch (2026-10-03): el tema "empleo" no basta en
# fuentes tier 3, hace falta un termino macro.
@pytest.mark.parametrize(
    ("title", "summary"),
    [
        (
            "A tough job market is pushing more young Americans to make a big bet: on themselves",
            "There has been a rise in entrepreneurship among young Americans.",
        ),
        ("Switching jobs to get higher pay works best in these industries", "Finding a new job is one way."),
    ],
)
def test_tier3_career_pieces_need_a_macro_term(title: str, summary: str) -> None:
    assert evaluate_news_quality(_item("MarketWatch", title, summary)).reason == "low_macro_relevance"


def test_tier3_labor_market_news_with_macro_terms_passes() -> None:
    item = _item(
        "MarketWatch",
        "Job openings are low and hiring is weak. Why the U.S. labor market won’t get better soon.",
        "War, high gas prices, rising interest rates and AI are keeping a lid on U.S. job creation.",
    )

    assert evaluate_news_quality(item).keep
