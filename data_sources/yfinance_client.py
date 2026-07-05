import logging
from dataclasses import dataclass

import yfinance as yf

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MarketAsset:
    symbol: str
    name: str
    yf_ticker: str


@dataclass(frozen=True)
class Quote:
    symbol: str
    name: str
    price: float | None
    change_pct: float | None
    source: str = "yfinance"


DEFAULT_ASSETS: tuple[MarketAsset, ...] = (
    MarketAsset("USDCLP", "USD/CLP", "CLP=X"),
    MarketAsset("COPPER", "Cobre", "HG=F"),
    MarketAsset("IPSA", "IPSA", "^IPSA"),
    MarketAsset("SP500", "S&P 500", "^GSPC"),
    MarketAsset("VOO", "VOO", "VOO"),
    MarketAsset("NASDAQ100", "Nasdaq 100", "^NDX"),
    MarketAsset("US10Y", "Treasury 10Y", "^TNX"),
    MarketAsset("DXY", "DXY", "DX-Y.NYB"),
    MarketAsset("GOLD", "Oro", "GC=F"),
    MarketAsset("WTI", "Petroleo WTI", "CL=F"),
    MarketAsset("BRENT", "Brent", "BZ=F"),
    MarketAsset("EUROSTOXX50", "EuroStoxx 50", "^STOXX50E"),
    MarketAsset("BOVESPA", "Bovespa", "^BVSP"),
    MarketAsset("MEXIPC", "Mexico IPC", "^MXX"),
    MarketAsset("USDBRL", "USD/BRL", "BRL=X"),
    MarketAsset("USDMXN", "USD/MXN", "MXN=X"),
    MarketAsset("USDCOP", "USD/COP", "COP=X"),
    MarketAsset("USDPEN", "USD/PEN", "PEN=X"),
)


class YFinanceClient:
    """Small yfinance wrapper that tolerates missing tickers and rate limits."""

    def __init__(self, timeout_seconds: float = 20.0) -> None:
        self.timeout_seconds = timeout_seconds

    def fetch_quotes(self, assets: tuple[MarketAsset, ...] = DEFAULT_ASSETS) -> list[Quote]:
        if not assets:
            return []

        try:
            quotes = self._fetch_batch(assets)
            if any(quote.price is not None for quote in quotes):
                return quotes
            logger.warning("No yfinance data returned from batch request")
            return quotes
        except Exception as exc:
            logger.warning(
                "yfinance batch request failed",
                extra={"error": type(exc).__name__},
                exc_info=True,
            )

        quotes: list[Quote] = []
        for asset in assets:
            quote = self._fetch_one(asset)
            quotes.append(quote)
        return quotes

    def _fetch_batch(self, assets: tuple[MarketAsset, ...]) -> list[Quote]:
        data = yf.download(
            tickers=[asset.yf_ticker for asset in assets],
            period="5d",
            interval="1d",
            auto_adjust=False,
            progress=False,
            threads=True,
            group_by="ticker",
            timeout=self.timeout_seconds,
        )
        return [self._quote_from_download(asset, data) for asset in assets]

    def _fetch_one(self, asset: MarketAsset) -> Quote:
        try:
            history = yf.download(
                tickers=asset.yf_ticker,
                period="5d",
                interval="1d",
                auto_adjust=False,
                progress=False,
                threads=False,
                timeout=self.timeout_seconds,
            )
        except Exception as exc:
            logger.warning(
                "yfinance request failed",
                extra={"symbol": asset.symbol, "ticker": asset.yf_ticker, "error": type(exc).__name__},
            )
            return Quote(asset.symbol, asset.name, None, None)

        return self._quote_from_download(asset, history)

    @staticmethod
    def _quote_from_download(asset: MarketAsset, history) -> Quote:
        closes = _extract_close_series(history, asset.yf_ticker)
        if closes is None:
            logger.warning(
                "No yfinance close column returned",
                extra={"symbol": asset.symbol, "ticker": asset.yf_ticker},
            )
            return Quote(asset.symbol, asset.name, None, None)

        if closes.empty:
            logger.warning(
                "No yfinance data returned",
                extra={"symbol": asset.symbol, "ticker": asset.yf_ticker},
            )
            return Quote(asset.symbol, asset.name, None, None)

        closes = closes.dropna()
        if closes.empty:
            return Quote(asset.symbol, asset.name, None, None)

        try:
            price = float(closes.iloc[-1])
            change_pct = None
            if len(closes) >= 2 and float(closes.iloc[-2]) != 0:
                previous = float(closes.iloc[-2])
                change_pct = ((price - previous) / previous) * 100
            return Quote(asset.symbol, asset.name, price, change_pct)
        except (ValueError, TypeError) as exc:
            logger.warning(
                "Failed to parse yfinance close prices",
                extra={"symbol": asset.symbol, "ticker": asset.yf_ticker, "error": type(exc).__name__},
            )
            return Quote(asset.symbol, asset.name, None, None)


def _extract_close_series(history, ticker: str):
    if history is None or getattr(history, "empty", True):
        return None

    columns = getattr(history, "columns", None)
    if columns is None:
        return None

    if getattr(columns, "nlevels", 1) > 1:
        level_0 = set(columns.get_level_values(0))
        if ticker in level_0:
            ticker_frame = history[ticker]
            if "Close" in ticker_frame:
                return ticker_frame["Close"]
        if "Close" in level_0:
            close_frame = history["Close"]
            if ticker in close_frame:
                return close_frame[ticker]
        return None

    if "Close" in history:
        return history["Close"]
    return None
