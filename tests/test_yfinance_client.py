from datetime import UTC, date, datetime, timedelta

import pandas as pd

from data_sources.yfinance_client import (
    DEFAULT_ASSETS,
    HISTORY_POINTS,
    MarketAsset,
    YFinanceClient,
)


def _recent_days(count: int) -> list[date]:
    # Fechas relativas a hoy: el cliente descarta series con ultimo cierre
    # de hace mas de STALE_AFTER_DAYS.
    today = datetime.now(UTC).date()
    return [today - timedelta(days=count - 1 - i) for i in range(count)]


def _ohlc_frame(closes: list[float], days: list | None = None) -> pd.DataFrame:
    index = pd.to_datetime(days or _recent_days(len(closes)))
    return pd.DataFrame(
        {
            "Open": closes,
            "High": [c * 1.01 for c in closes],
            "Low": [c * 0.99 for c in closes],
            "Close": closes,
        },
        index=index,
    )


def _batch(frames: dict[str, pd.DataFrame]) -> pd.DataFrame:
    return pd.concat(frames, axis=1)


def _patch_download(monkeypatch, fake) -> None:
    import data_sources.yfinance_client as module

    monkeypatch.setattr(module.yf, "download", fake)


def test_yfinance_client_parses_batch_download(monkeypatch) -> None:
    copper_ticker = "HG" + "=F"
    data = _batch({
        "CLP=X": _ohlc_frame([900.0, 909.0]),
        copper_ticker: _ohlc_frame([4.0, 4.2]),
    })

    def fake_download(**kwargs):
        assert kwargs["tickers"] == ["CLP=X", copper_ticker]
        assert kwargs["progress"] is False
        assert kwargs["period"] == "1mo"
        assert kwargs["interval"] == "1d"
        assert "session" not in kwargs
        return data

    _patch_download(monkeypatch, fake_download)

    quotes = YFinanceClient().fetch_quotes((
        MarketAsset("USDCLP", "USD/CLP", "CLP=X"),
        MarketAsset("COPPER", "Cobre", copper_ticker),
    ))

    assert quotes[0].symbol == "USDCLP"
    assert quotes[0].price == 909.0
    assert quotes[0].change_pct == 1.0
    assert quotes[0].history == (900.0, 909.0)
    assert quotes[1].symbol == "COPPER"
    assert round(quotes[1].change_pct or 0, 2) == 5.0


def test_yfinance_client_does_not_retry_every_symbol_when_batch_is_empty(monkeypatch) -> None:
    calls = 0

    def fake_download(**kwargs):
        nonlocal calls
        calls += 1
        return pd.DataFrame()

    _patch_download(monkeypatch, fake_download)
    assets = (
        MarketAsset("SP500", "S&P 500", "^GSPC"),
        MarketAsset("GOLD", "Oro", "GC=F"),
    )

    quotes = YFinanceClient().fetch_quotes(assets)

    assert calls == 1
    assert [quote.symbol for quote in quotes] == ["SP500", "GOLD"]
    assert all(quote.price is None for quote in quotes)


def test_yfinance_client_falls_back_per_ticker_when_batch_raises(monkeypatch) -> None:
    calls: list[object] = []

    def fake_download(**kwargs):
        calls.append(kwargs["tickers"])
        if isinstance(kwargs["tickers"], list):
            raise RuntimeError("boom")
        return _ohlc_frame([10.0, 11.0])

    _patch_download(monkeypatch, fake_download)

    quotes = YFinanceClient().fetch_quotes((
        MarketAsset("SP500", "S&P 500", "^GSPC"),
        MarketAsset("GOLD", "Oro", "GC=F"),
    ))

    assert calls == [["^GSPC", "GC=F"], "^GSPC", "GC=F"]
    assert [q.price for q in quotes] == [11.0, 11.0]


def test_yfinance_client_groups_assets_by_interval_and_keeps_order(monkeypatch) -> None:
    requested: list[tuple[str, tuple[str, ...]]] = []

    def fake_download(**kwargs):
        tickers = tuple(kwargs["tickers"])
        requested.append((kwargs["interval"], tickers))
        if kwargs["interval"] == "1h":
            days = _recent_days(2)
            index = pd.to_datetime([
                datetime(days[0].year, days[0].month, days[0].day, 10),
                datetime(days[0].year, days[0].month, days[0].day, 15),
                datetime(days[1].year, days[1].month, days[1].day, 10),
                datetime(days[1].year, days[1].month, days[1].day, 15),
            ])
            frame = pd.DataFrame(
                {"Open": [100.0] * 4, "High": [120.0] * 4, "Low": [90.0] * 4, "Close": [100.0, 110.0, 105.0, 99.0]},
                index=index,
            )
            return _batch({"MXIPSAGC.SN": frame})
        return _batch({"^GSPC": _ohlc_frame([10.0, 11.0])})

    _patch_download(monkeypatch, fake_download)

    quotes = YFinanceClient().fetch_quotes((
        MarketAsset("IPSA", "IPSA", "MXIPSAGC.SN", interval="1h"),
        MarketAsset("SP500", "S&P 500", "^GSPC"),
    ))

    assert requested == [("1h", ("MXIPSAGC.SN",)), ("1d", ("^GSPC",))]
    assert [q.symbol for q in quotes] == ["IPSA", "SP500"]
    # Velas horarias -> ultimo cierre de cada dia: 110 y luego 99.
    assert quotes[0].history == (110.0, 99.0)
    assert quotes[0].price == 99.0
    assert round(quotes[0].change_pct or 0, 2) == -10.0


def test_yfinance_client_discards_inconsistent_series(monkeypatch) -> None:
    frame = _ohlc_frame([3.27, 3.28, 3.27, 3.28])
    # Close fuera de [Low, High] en la mayoria de las velas (caso PEN=X).
    frame["Close"] = [3.40, 3.10, 3.45, 3.28]
    _patch_download(monkeypatch, lambda **kwargs: _batch({"PEN=X": frame}))

    quotes = YFinanceClient().fetch_quotes((MarketAsset("USDPEN", "USD/PEN", "PEN=X"),))

    assert quotes[0].price is None
    assert quotes[0].history == ()


def test_yfinance_client_drops_isolated_inconsistent_bar(monkeypatch) -> None:
    closes = [900.0, 901.0, 902.0, 903.0, 904.0]
    frame = _ohlc_frame(closes)
    frame.loc[frame.index[2], "Close"] = 990.0  # vela aislada con error
    _patch_download(monkeypatch, lambda **kwargs: _batch({"CLP=X": frame}))

    quotes = YFinanceClient().fetch_quotes((MarketAsset("USDCLP", "USD/CLP", "CLP=X"),))

    assert quotes[0].history == (900.0, 901.0, 903.0, 904.0)
    assert quotes[0].price == 904.0


def test_yfinance_client_discards_stale_series(monkeypatch) -> None:
    old = [datetime.now(UTC).date() - timedelta(days=40 - i) for i in range(3)]
    _patch_download(monkeypatch, lambda **kwargs: _batch({"SPIPSA.SN": _ohlc_frame([1.0, 2.0, 3.0], old)}))

    quotes = YFinanceClient().fetch_quotes((MarketAsset("IPSA", "IPSA", "SPIPSA.SN"),))

    assert quotes[0].price is None


def test_yfinance_client_caps_history_points(monkeypatch) -> None:
    closes = [float(i) for i in range(1, 31)]
    _patch_download(monkeypatch, lambda **kwargs: _batch({"^GSPC": _ohlc_frame(closes)}))

    quotes = YFinanceClient().fetch_quotes((MarketAsset("SP500", "S&P 500", "^GSPC"),))

    assert len(quotes[0].history) == HISTORY_POINTS
    assert quotes[0].history[-1] == 30.0


def test_default_ipsa_uses_hourly_bolsa_santiago_ticker() -> None:
    ipsa = next(a for a in DEFAULT_ASSETS if a.symbol == "IPSA")
    assert ipsa.yf_ticker == "MXIPSAGC.SN"
    assert ipsa.interval == "1h"
