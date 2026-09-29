import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Protocol

from app.config import get_settings
from data_sources.bcentral_client import BCentralClient
from data_sources.yfinance_client import DEFAULT_ASSETS, Quote, YFinanceClient
from storage.models import MarketSnapshot

logger = logging.getLogger(__name__)

# Tipos de cambio que se toman del BCCh en vez de Yahoo: (simbolo, nombre,
# atributo de Settings con el codigo de serie). USD/PEN salio de yfinance
# porque PEN=X traia velas inconsistentes (sep-2026).
BCENTRAL_FX_SERIES: tuple[tuple[str, str, str], ...] = (
    ("USDPEN", "USD/PEN", "bcentral_usdpen_series"),
)


MACRO_INDICATOR_SYMBOLS: tuple[str, ...] = ("TPM", "IPC", "DESEMPLEO")


def expected_market_symbols() -> list[str]:
    """Simbolos que cada corrida deberia traer (para la salud de fuentes)."""
    return [
        *(asset.symbol for asset in DEFAULT_ASSETS),
        *(symbol for symbol, _, _ in BCENTRAL_FX_SERIES),
        *MACRO_INDICATOR_SYMBOLS,
    ]


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

        # yfinance y el BCCh son servicios independientes: se consultan en
        # paralelo y el tiempo total queda acotado por el mas lento.
        with ThreadPoolExecutor(max_workers=4) as executor:
            fx_future = executor.submit(self._collect_bcentral_fx)
            macro_future = executor.submit(self._collect_bcentral_indicators, timestamp)
            try:
                quotes = self.market_client.fetch_quotes()
            except Exception:
                logger.warning("Market data provider failed", exc_info=True)
                quotes = []
            # El fallback se evalua solo con yfinance: un tipo de cambio del
            # BCCh no debe ocultar que el proveedor principal no trajo datos.
            quotes = self._with_fallback_quotes(quotes)
            quotes = _merge_quotes(quotes, fx_future.result())
            macro = macro_future.result()

        snapshots = [
            MarketSnapshot(
                timestamp=timestamp,
                symbol=quote.symbol,
                name=quote.name,
                price=quote.price,
                change_pct=quote.change_pct,
                source=quote.source,
                history=quote.history,
            )
            for quote in quotes
        ]
        snapshots.extend(macro)
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
            extra={"provider": type(self.fallback_market_client).__name__, "count": len(fallback_quotes)},
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

    def _collect_bcentral_fx(self) -> list[Quote]:
        settings = getattr(self.bcentral_client, "settings", None) or get_settings()
        quotes: list[Quote] = []
        for symbol, name, setting in BCENTRAL_FX_SERIES:
            try:
                quote = self.bcentral_client.fetch_fx_quote(getattr(settings, setting), symbol, name)
            except Exception:
                logger.warning("Failed to fetch BCentral FX series", extra={"symbol": symbol}, exc_info=True)
                continue
            if quote is not None:
                quotes.append(quote)
        return quotes

    def _collect_bcentral_indicators(self, timestamp: datetime) -> list[MarketSnapshot]:
        indicators = (
            ("TPM", "TPM Chile", self.bcentral_client.fetch_policy_rate),
            ("IPC", "IPC / Inflacion Chile", self.bcentral_client.fetch_inflation),
            ("DESEMPLEO", "Desempleo Chile", self.bcentral_client.fetch_unemployment),
        )
        with ThreadPoolExecutor(max_workers=len(indicators)) as executor:
            futures = [(symbol, name, executor.submit(fetch)) for symbol, name, fetch in indicators]
        items: list[MarketSnapshot] = []
        for symbol, name, future in futures:
            try:
                value = future.result()
            except Exception:
                logger.warning("Failed to fetch BCentral indicator", extra={"symbol": symbol}, exc_info=True)
                continue
            items.append(MarketSnapshot(timestamp, symbol, name, value, None, "bcentral"))
        return items


def _merge_quotes(quotes: list[Quote], extra: list[Quote]) -> list[Quote]:
    """Agrega `extra` reemplazando cotizaciones sin datos del mismo simbolo."""
    merged = list(quotes)
    by_symbol = {quote.symbol: idx for idx, quote in enumerate(merged)}
    for quote in extra:
        idx = by_symbol.get(quote.symbol)
        if idx is None:
            merged.append(quote)
        elif merged[idx].price is None:
            merged[idx] = quote
    return merged


class NoopMarketClient:
    def fetch_quotes(self) -> list[Quote]:
        return []


def _build_fallback_market_client() -> MarketQuoteClient:
    # Google Finance ya no se usa como fallback (ver decision del club, 2026-09).
    # yfinance es la unica fuente de datos de mercado; si falla, la tabla de
    # activos del correo queda vacia ("Mercado cerrado o sin datos disponibles").
    return NoopMarketClient()


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
