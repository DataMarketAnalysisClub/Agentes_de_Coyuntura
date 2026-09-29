import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from app.config import get_settings
from data_sources.bcentral_client import BCentralClient
from data_sources.yfinance_client import DEFAULT_ASSETS, Quote, YFinanceClient
from storage.models import MarketSnapshot

logger = logging.getLogger(__name__)

# Tipos de cambio que se toman del BCCh en vez de Yahoo: (simbolo, nombre,
# atributo de Settings con el codigo de serie). USD/PEN salio de yfinance
# porque PEN=X traia velas inconsistentes (sep-2026).
# Dolar observado, UF y cobre BML son referencias oficiales diarias: se
# muestran junto a las de Yahoo (intradia), no las reemplazan.
BCENTRAL_FX_SERIES: tuple[tuple[str, str, str], ...] = (
    ("USDPEN", "USD/PEN", "bcentral_usdpen_series"),
    ("DOLAR_OBS", "Dólar observado", "bcentral_dolar_observado_series"),
    ("UF", "UF", "bcentral_uf_series"),
    ("COBRE_BML", "Cobre BML", "bcentral_copper_series"),
)


@dataclass(frozen=True)
class MacroIndicator:
    symbol: str
    name: str
    setting: str  # atributo de Settings con el codigo de serie
    lookback_days: int
    monthly: bool  # rotula el periodo como "ago-26" (mensual) o "29-09" (diario)


# Indicadores del BCCh: nivel del ultimo dato, su periodo y el cambio contra
# el dato anterior. Codigos verificados con SearchSeries el 2026-09-29.
MACRO_INDICATORS: tuple[MacroIndicator, ...] = (
    MacroIndicator("TPM", "TPM", "bcentral_tpm_series", 120, monthly=False),
    MacroIndicator("IPC12", "IPC 12 meses", "bcentral_ipc12_series", 400, monthly=True),
    MacroIndicator("IPC", "IPC mensual", "bcentral_ipc_series", 400, monthly=True),
    MacroIndicator("IMACEC", "IMACEC 12 meses", "bcentral_imacec_series", 400, monthly=True),
    # Trimestre movil del INE: el periodo es el ultimo mes del trimestre.
    MacroIndicator("DESEMPLEO", "Desempleo", "bcentral_unemployment_series", 400, monthly=True),
)

MACRO_INDICATOR_SYMBOLS: tuple[str, ...] = tuple(indicator.symbol for indicator in MACRO_INDICATORS)

_MONTH_ABBR = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def format_period(observed_at: date | None, monthly: bool) -> str:
    """"ago-26" para datos mensuales, "29-09" para diarios, '' sin fecha."""
    if observed_at is None:
        return ""
    if monthly:
        return f"{_MONTH_ABBR[observed_at.month - 1]}-{observed_at:%y}"
    return f"{observed_at:%d-%m}"


def expected_market_symbols() -> list[str]:
    """Simbolos que cada corrida deberia traer (para la salud de fuentes)."""
    return [
        *(asset.symbol for asset in DEFAULT_ASSETS),
        *(symbol for symbol, _, _ in BCENTRAL_FX_SERIES),
        *MACRO_INDICATOR_SYMBOLS,
    ]


# Antiguedad maxima del ultimo dato valido que se muestra cuando una fuente
# no trae datos hoy (rotulado con su fecha en el correo).
LAST_GOOD_MAX_AGE_DAYS = 5


def market_display_names(snapshots: list[MarketSnapshot] = ()) -> dict[str, str]:
    """Nombre legible por simbolo esperado (para avisos al lector)."""
    names = {asset.symbol: asset.name for asset in DEFAULT_ASSETS}
    names.update({symbol: name for symbol, name, _ in BCENTRAL_FX_SERIES})
    names.update({indicator.symbol: indicator.name for indicator in MACRO_INDICATORS})
    names.update({snapshot.symbol: snapshot.name for snapshot in snapshots if snapshot.name})
    return names


def with_last_good_prices(
    snapshots: list[MarketSnapshot],
    last_good: dict[str, MarketSnapshot],
    now: datetime,
    expected_symbols: list[str] | None = None,
) -> tuple[list[MarketSnapshot], set[str]]:
    """Completa simbolos sin precio con su ultimo dato valido reciente, rotulado.

    Devuelve (snapshots para mostrar, simbolos completados). El dato viejo
    solo trae precio: sin variacion ni historia, y con `as_of` para que el
    correo muestre su fecha. Es solo para mostrar: no se debe persistir ni
    entregar a la IA como si fuera de hoy.
    """
    min_timestamp = now - timedelta(days=LAST_GOOD_MAX_AGE_DAYS)
    by_symbol = {snapshot.symbol: snapshot for snapshot in snapshots}
    order = list(dict.fromkeys([*(expected_symbols or []), *by_symbol]))
    display: list[MarketSnapshot] = []
    covered: set[str] = set()
    for symbol in order:
        current = by_symbol.get(symbol)
        if current is not None and current.price is not None:
            display.append(current)
            continue
        stored = last_good.get(symbol)
        if stored is not None and stored.timestamp >= min_timestamp:
            display.append(
                MarketSnapshot(
                    timestamp=current.timestamp if current else now,
                    symbol=symbol,
                    name=(current.name if current else "") or stored.name,
                    price=stored.price,
                    change_pct=None,
                    source=stored.source,
                    as_of=stored.timestamp,
                )
            )
            covered.add(symbol)
        elif current is not None:
            display.append(current)
    return display, covered


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
        settings = getattr(self.bcentral_client, "settings", None) or get_settings()
        with ThreadPoolExecutor(max_workers=len(MACRO_INDICATORS)) as executor:
            futures = [
                (
                    indicator,
                    executor.submit(
                        self.bcentral_client.fetch_indicator,
                        getattr(settings, indicator.setting),
                        indicator.lookback_days,
                    ),
                )
                for indicator in MACRO_INDICATORS
            ]
        items: list[MarketSnapshot] = []
        for indicator, future in futures:
            try:
                reading = future.result()
            except Exception:
                logger.warning("Failed to fetch BCentral indicator", extra={"symbol": indicator.symbol}, exc_info=True)
                continue
            if reading is None:
                # Sin dato: la salud de fuentes y la linea "Sin datos" lo reportan.
                items.append(MarketSnapshot(timestamp, indicator.symbol, indicator.name, None, None, "bcentral"))
                continue
            change = None if reading.previous is None else round(reading.value - reading.previous, 4)
            items.append(
                MarketSnapshot(
                    timestamp,
                    indicator.symbol,
                    indicator.name,
                    reading.value,
                    None,
                    "bcentral",
                    period=format_period(reading.observed_at, indicator.monthly),
                    change_points=change,
                )
            )
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


CHILE_TZ = ZoneInfo("America/Santiago")


def format_as_of(snapshot: MarketSnapshot) -> str:
    """Rotulo "al DD-MM" (hora de Chile) para un ultimo dato valido, o ''."""
    if snapshot.as_of is None:
        return ""
    return f"al {snapshot.as_of.astimezone(CHILE_TZ):%d-%m}"


def format_market_line(snapshot: MarketSnapshot) -> str:
    price = "s/d" if snapshot.price is None else f"{snapshot.price:,.2f}"
    change = "s/d" if snapshot.change_pct is None else f"{snapshot.change_pct:+.2f}%"
    as_of = format_as_of(snapshot)
    return f"{snapshot.name}: {price} ({as_of or change})"
