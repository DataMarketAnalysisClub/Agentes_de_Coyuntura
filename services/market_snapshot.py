import logging
from datetime import UTC, datetime
from typing import Protocol

from data_sources.bcentral_client import BCentralClient
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
    ) -> None:
        self.market_client = market_client or YFinanceClient()
        self.bcentral_client = bcentral_client or BCentralClient()

    def collect(self) -> list[MarketSnapshot]:
        timestamp = datetime.now(UTC)
        snapshots: list[MarketSnapshot] = []

        try:
            quotes = self.market_client.fetch_quotes()
        except Exception:
            logger.warning("Market data provider failed", exc_info=True)
            quotes = []

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


def format_market_line(snapshot: MarketSnapshot) -> str:
    price = "s/d" if snapshot.price is None else f"{snapshot.price:,.2f}"
    change = "s/d" if snapshot.change_pct is None else f"{snapshot.change_pct:+.2f}%"
    return f"{snapshot.name}: {price} ({change})"
