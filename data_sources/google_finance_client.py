import logging
import re
from dataclasses import dataclass

from bs4 import BeautifulSoup

from app.http_client import CircuitBreakerError, ResilientHttpClient
from data_sources.yfinance_client import MarketAsset, Quote

logger = logging.getLogger(__name__)

GOOGLE_FINANCE_MARKETS_URL = "https://www.google.com/finance/markets/indexes?hl=en"
GOOGLE_FINANCE_TIMEOUT_SECONDS = 12.0

WATCHED_MARKETS = {
    "Dow Jones",
    "S&P 500",
    "Nasdaq",
    "Russell",
    "VIX",
    "DAX",
    "STOXX 50",
    "Nikkei 225",
    "SSE",
    "HSI",
    "S&P LATAM 40",
    "IBOVESPA",
    "Dow Futures",
    "S&P Futures",
    "Nasdaq Futures",
    "Gold",
    "Crude Oil",
}

GOOGLE_FINANCE_MARKET_ASSETS = {
    "S&P 500": MarketAsset("SP500", "S&P 500", "^GSPC"),
    "Nasdaq": MarketAsset("NASDAQ100", "Nasdaq 100", "^NDX"),
    "STOXX 50": MarketAsset("EUROSTOXX50", "EuroStoxx 50", "^STOXX50E"),
    "IBOVESPA": MarketAsset("BOVESPA", "Bovespa", "^BVSP"),
    "Gold": MarketAsset("GOLD", "Oro", "GC=F"),
    "Crude Oil": MarketAsset("WTI", "Petroleo WTI", "CL=F"),
}

PCT_RE = re.compile(r"^[+-]\d+(?:\.\d+)?%$")
PRICE_RE = re.compile(r"^\$?\d[\d,]*(?:\.\d+)?$")


@dataclass(frozen=True)
class GoogleFinanceMarketItem:
    name: str
    price: float | None
    change_pct: float | None


class GoogleFinanceClient:
    """Best-effort reader for the public Google Finance market summary page."""

    def __init__(self, http_client: ResilientHttpClient | None = None) -> None:
        self._http_client = http_client

    def _get_client(self) -> ResilientHttpClient:
        if self._http_client is None:
            return ResilientHttpClient(
                name="google_finance",
                timeout=GOOGLE_FINANCE_TIMEOUT_SECONDS,
                retries=1,
            )
        return self._http_client

    def fetch_market_summary(self) -> list[GoogleFinanceMarketItem]:
        try:
            response = self._get_client().get(
                GOOGLE_FINANCE_MARKETS_URL,
                headers={"User-Agent": "DMAC market brief research bot"},
            )
            response.raise_for_status()
        except CircuitBreakerError:
            logger.warning("Google Finance circuit breaker open")
            return []
        except Exception:
            logger.warning("Failed to fetch Google Finance market summary", exc_info=True)
            return []
        return parse_market_summary(response.text)


class GoogleFinanceQuoteClient:
    """Convert Google Finance market summary rows into normalized quotes."""

    def __init__(self, market_client: GoogleFinanceClient | None = None) -> None:
        self.market_client = market_client or GoogleFinanceClient()

    def fetch_quotes(self) -> list[Quote]:
        quotes: list[Quote] = []
        for item in self.market_client.fetch_market_summary():
            asset = GOOGLE_FINANCE_MARKET_ASSETS.get(item.name)
            if asset is None:
                continue
            quotes.append(
                Quote(
                    symbol=asset.symbol,
                    name=asset.name,
                    price=item.price,
                    change_pct=item.change_pct,
                    source="google_finance",
                )
            )
        return quotes


def parse_market_summary(html: str) -> list[GoogleFinanceMarketItem]:
    soup = BeautifulSoup(html, "lxml")
    lines = [line.strip() for line in soup.get_text("\n").splitlines() if line.strip()]
    items: list[GoogleFinanceMarketItem] = []
    seen: set[str] = set()

    for idx, line in enumerate(lines):
        if line not in WATCHED_MARKETS or line in seen:
            continue

        window = lines[idx + 1: idx + 12]
        pct_text = next((candidate for candidate in window if PCT_RE.match(candidate)), "")
        price_text = next((candidate for candidate in window if PRICE_RE.match(candidate)), "")
        if not pct_text and not price_text:
            continue

        items.append(
            GoogleFinanceMarketItem(
                name=line,
                price=_parse_float(price_text),
                change_pct=_parse_percent(pct_text),
            )
        )
        seen.add(line)

    return items


def _parse_float(value: str) -> float | None:
    if not value:
        return None
    try:
        return float(value.replace("$", "").replace(",", ""))
    except ValueError:
        return None


def _parse_percent(value: str) -> float | None:
    if not value:
        return None
    try:
        return float(value.replace("%", ""))
    except ValueError:
        return None
