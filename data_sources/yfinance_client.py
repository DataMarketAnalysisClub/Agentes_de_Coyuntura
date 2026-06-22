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

    def fetch_quotes(self, assets: tuple[MarketAsset, ...] = DEFAULT_ASSETS) -> list[Quote]:
        quotes: list[Quote] = []
        for asset in assets:
            quote = self._fetch_one(asset)
            quotes.append(quote)
        return quotes

    @staticmethod
    def _fetch_one(asset: MarketAsset) -> Quote:
        try:
            ticker = yf.Ticker(asset.yf_ticker)
            history = ticker.history(period="5d", interval="1d", auto_adjust=False)
        except Exception as exc:
            logger.warning(
                "yfinance request failed",
                extra={"symbol": asset.symbol, "error": type(exc).__name__},
            )
            return Quote(asset.symbol, asset.name, None, None)

        if history is None or history.empty or "Close" not in history:
            logger.warning("No yfinance data returned", extra={"symbol": asset.symbol})
            return Quote(asset.symbol, asset.name, None, None)

        closes = history["Close"].dropna()
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
                extra={"symbol": asset.symbol, "error": type(exc).__name__},
            )
            return Quote(asset.symbol, asset.name, None, None)
