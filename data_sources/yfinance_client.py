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
    """Small yfinance wrapper that tolerates missing tickers."""

    def fetch_quotes(self, assets: tuple[MarketAsset, ...] = DEFAULT_ASSETS) -> list[Quote]:
        quotes: list[Quote] = []
        for asset in assets:
            try:
                history = yf.Ticker(asset.yf_ticker).history(period="5d", interval="1d")
                if history.empty or "Close" not in history:
                    logger.warning("No yfinance data returned", extra={"symbol": asset.symbol})
                    quotes.append(Quote(asset.symbol, asset.name, None, None))
                    continue

                closes = history["Close"].dropna()
                if closes.empty:
                    quotes.append(Quote(asset.symbol, asset.name, None, None))
                    continue

                price = float(closes.iloc[-1])
                change_pct = None
                if len(closes) >= 2 and float(closes.iloc[-2]) != 0:
                    previous = float(closes.iloc[-2])
                    change_pct = ((price - previous) / previous) * 100
                quotes.append(Quote(asset.symbol, asset.name, price, change_pct))
            except Exception:
                logger.warning("Failed to fetch yfinance quote", extra={"symbol": asset.symbol}, exc_info=True)
                quotes.append(Quote(asset.symbol, asset.name, None, None))
        return quotes
