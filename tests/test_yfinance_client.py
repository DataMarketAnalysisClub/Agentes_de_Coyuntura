from datetime import datetime

import pandas as pd

from data_sources.yfinance_client import MarketAsset, YFinanceClient


def test_yfinance_client_parses_batch_download(monkeypatch) -> None:
    copper_ticker = "HG" + "=F"
    dates = pd.to_datetime([datetime(2026, 1, 1), datetime(2026, 1, 2)])
    columns = pd.MultiIndex.from_tuples([
        ("CLP=X", "Close"),
        (copper_ticker, "Close"),
    ])
    data = pd.DataFrame([[900.0, 4.0], [909.0, 4.2]], index=dates, columns=columns)

    def fake_download(**kwargs):
        assert kwargs["tickers"] == ["CLP=X", copper_ticker]
        assert kwargs["progress"] is False
        return data

    import data_sources.yfinance_client as module

    monkeypatch.setattr(module.yf, "download", fake_download)
    client = YFinanceClient()

    quotes = client.fetch_quotes((
        MarketAsset("USDCLP", "USD/CLP", "CLP=X"),
        MarketAsset("COPPER", "Cobre", copper_ticker),
    ))

    assert quotes[0].symbol == "USDCLP"
    assert quotes[0].price == 909.0
    assert quotes[0].change_pct == 1.0
    assert quotes[1].symbol == "COPPER"
    assert round(quotes[1].change_pct or 0, 2) == 5.0


def test_yfinance_client_does_not_retry_every_symbol_when_batch_is_empty(monkeypatch) -> None:
    calls = 0

    def fake_download(**kwargs):
        nonlocal calls
        calls += 1
        return pd.DataFrame()

    import data_sources.yfinance_client as module

    monkeypatch.setattr(module.yf, "download", fake_download)
    assets = (
        MarketAsset("SP500", "S&P 500", "^GSPC"),
        MarketAsset("GOLD", "Oro", "GC=F"),
    )

    quotes = YFinanceClient().fetch_quotes(assets)

    assert calls == 1
    assert [quote.symbol for quote in quotes] == ["SP500", "GOLD"]
    assert all(quote.price is None for quote in quotes)
