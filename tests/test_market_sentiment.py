from datetime import UTC, datetime

from data_sources.google_finance_client import GoogleFinanceMarketItem
from services.market_sentiment import build_market_sentiment
from storage.models import MarketSnapshot


def test_build_market_sentiment_uses_google_finance_and_yfinance() -> None:
    now = datetime.now(UTC)
    snapshots = [
        MarketSnapshot(now, "SP500", "S&P 500", 7000.0, 1.0, "yfinance"),
        MarketSnapshot(now, "DXY", "DXY", 100.0, -0.5, "yfinance"),
    ]
    google_items = [
        GoogleFinanceMarketItem("Nasdaq", 25000.0, 2.0),
        GoogleFinanceMarketItem("VIX", 17.0, -4.0),
    ]

    sentiment = build_market_sentiment(snapshots, google_items)

    assert sentiment.score > 60
    assert sentiment.label in {"Levemente positivo", "Riesgo positivo"}
    assert "Google Finance" in sentiment.source
    assert any("Nasdaq" in driver for driver in sentiment.drivers)


def test_build_market_sentiment_handles_missing_data() -> None:
    sentiment = build_market_sentiment([], [])

    assert sentiment.label == "Neutral"
    assert sentiment.score == 50
