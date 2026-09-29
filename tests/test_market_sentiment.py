from datetime import UTC, datetime

from services.market_sentiment import build_market_sentiment
from storage.models import MarketSnapshot


def test_build_market_sentiment_uses_yfinance_snapshots() -> None:
    now = datetime.now(UTC)
    snapshots = [
        MarketSnapshot(now, "SP500", "S&P 500", 7000.0, 1.0, "yfinance"),
        MarketSnapshot(now, "NASDAQ100", "Nasdaq 100", 25000.0, 2.0, "yfinance"),
        MarketSnapshot(now, "DXY", "DXY", 100.0, -0.5, "yfinance"),
        MarketSnapshot(now, "VIX", "VIX", 17.0, -4.0, "yfinance"),
    ]

    sentiment = build_market_sentiment(snapshots)

    assert sentiment.score > 60
    assert sentiment.label in {"Levemente positivo", "Riesgo positivo"}
    assert sentiment.source == "yfinance"
    assert any("Nasdaq" in driver for driver in sentiment.drivers)


def test_build_market_sentiment_handles_missing_data() -> None:
    sentiment = build_market_sentiment([])

    assert sentiment.label == "Neutral"
    assert sentiment.score == 50
