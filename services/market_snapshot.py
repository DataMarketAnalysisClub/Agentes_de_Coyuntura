import logging
from datetime import UTC, datetime
from typing import Protocol

from app.config import get_settings
from data_sources.bcentral_client import BCentralClient
from data_sources.google_finance_client import GoogleFinanceQuoteClient
from data_sources.yfinance_client import Quote, YFinanceClient
from storage.models import MarketSnapshot

logger = logging.getLogger(__name__)


class MarketQuoteClient(Protocol):
    def fetch_quotes(self) -> list[Quote]: ...


class MarketSnapshotService:
    """Builds a normalized market snapshot from available providers."""

    def __init__(
        self,
        market_client: MarketQuoteClient | None = None,
        bcentral_client: BCentralClient | None = None,
        fallback_market_client: MarketQuoteClient | None = None,
    ) -> None:
        self.market_client = market_client or _build_market_client()
        self.bcentral_client = bcentral_client or BCentralClient()
        self.fallback_market_client = (
            fallback_market_client
            if fallback_market_client is not None
            else _build_fallback_market_client() if market_client is None else NoopMarketClient()
        )

    def collect(self) -> list[MarketSnapshot]:
        timestamp = datetime.now(UTC)
        snapshots: list[MarketSnapshot] = []

        try:
            quotes = self.market_client.fetch_quotes()
        except Exception:
            logger.warning("Market data provider failed", exc_info=True)
            quotes = []

        quotes = self._with_fallback_quotes(quotes)

        for quote in quotes:
            snapshots.append(
                MarketSnapshot(
                    timestamp=timestamp,
                    symbol=quote.symbol,
                    name=quote.name,
                    price=quote.price,
                    change_pct=quote.change_pct,
                    source=quote.source,
                )
            )

        snapshots.extend(self._collect_bcentral_placeholders(timestamp))
        return snapshots

    def _with_fallback_quotes(self, quotes: list[Quote]) -> list[Quote]:
        if any(quote.price is not None or quote.change_pct is not None for quote in quotes):
            return quotes

        try:
            fallback_quotes = self.fallback_market_client.fetch_quotes()
        except Exception:
            logger.warning("Fallback market data provider failed", exc_info=True)
            return quotes

        if not fallback_quotes:
            return quotes

        logger.warning(
            "Using fallback market data provider",
            extra={"provider": "google_finance", "count": len(fallback_quotes)},
        )
        by_symbol = {quote.symbol: idx for idx, quote in enumerate(quotes)}
        merged = list(quotes)
        for fallback_quote in fallback_quotes:
            idx = by_symbol.get(fallback_quote.symbol)
            if idx is None:
                merged.append(fallback_quote)
                continue
            quote = merged[idx]
            if quote.price is None and quote.change_pct is None:
                merged[idx] = fallback_quote
        return merged

    def _collect_bcentral_placeholders(self, timestamp: datetime) -> list[MarketSnapshot]:
        items: list[MarketSnapshot] = []
        try:
            tpm = self.bcentral_client.fetch_policy_rate()
            items.append(MarketSnapshot(timestamp, "TPM", "TPM Chile", tpm, None, "bcentral"))
        except Exception:
            logger.warning("Failed to fetch TPM placeholder", exc_info=True)

        try:
            inflation = self.bcentral_client.fetch_inflation()
            items.append(MarketSnapshot(timestamp, "IPC", "IPC / Inflacion Chile", inflation, None, "bcentral"))
        except Exception:
            logger.warning("Failed to fetch inflation placeholder", exc_info=True)
        return items


class NoopMarketClient:
    def fetch_quotes(self) -> list[Quote]:
        return []


def _build_fallback_market_client() -> MarketQuoteClient:
    provider = get_settings().market_data_provider.strip().lower()
    if provider in {"none", "disabled", "off"}:
        return NoopMarketClient()
    return GoogleFinanceQuoteClient()


def _build_market_client() -> MarketQuoteClient:
    provider = get_settings().market_data_provider.strip().lower()
    if provider in {"", "yfinance"}:
        return YFinanceClient()
    if provider in {"none", "disabled", "off"}:
        logger.warning("Market data provider disabled by configuration")
        return NoopMarketClient()
    logger.warning("Unknown market data provider; falling back to yfinance", extra={"provider": provider})
    return YFinanceClient()


def format_market_line(snapshot: MarketSnapshot) -> str:
    price = "s/d" if snapshot.price is None else f"{snapshot.price:,.2f}"
    change = "s/d" if snapshot.change_pct is None else f"{snapshot.change_pct:+.2f}%"
    return f"{snapshot.name}: {price} ({change})"
