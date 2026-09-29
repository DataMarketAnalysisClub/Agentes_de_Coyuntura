import logging
import random
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)

# yfinance >= 1.0 depende de curl_cffi y crea por su cuenta una sesion que
# imita el fingerprint TLS de Chrome (la mitigacion contra el bloqueo anti-bot
# de Yahoo). Inyectar una sesion propia ya no es necesario y la propia libreria
# recomienda no hacerlo ("stop setting session, let yfinance handle").
#
# Reintentos nativos de yfinance: solo aplican a errores transitorios de red
# (timeouts, conexion cortada), no a "sin datos" ni a rate limit.
YF_NETWORK_RETRIES = 2
if hasattr(yf, "config"):
    yf.config.network.retries = max(yf.config.network.retries, YF_NETWORK_RETRIES)

# Cantidad de cierres diarios que se conservan para graficar (~1 mes habil).
HISTORY_POINTS = 22
# Si el ultimo cierre es mas antiguo que esto, el dato se considera vencido
# (ticker abandonado por Yahoo) y no se muestra como si fuera de hoy.
STALE_AFTER_DAYS = 7
# Fraccion de velas con Close fuera de [Low, High] sobre la cual la serie
# completa se descarta por inconsistente (ej. PEN=X en sep-2026: 16/23 velas).
MAX_INCONSISTENT_BAR_RATIO = 0.25
_OHLC_TOLERANCE = 1e-4


@dataclass(frozen=True)
class MarketAsset:
    symbol: str
    name: str
    yf_ticker: str
    # "1h" para tickers cuyo historial diario en Yahoo esta incompleto: los
    # cierres diarios se reconstruyen desde las velas horarias.
    interval: str = "1d"


@dataclass(frozen=True)
class Quote:
    symbol: str
    name: str
    price: float | None
    change_pct: float | None
    source: str = "yfinance"
    # Cierres diarios recientes (antiguo -> reciente) para graficos.
    history: tuple[float, ...] = field(default=(), compare=False, repr=False)


DEFAULT_ASSETS: tuple[MarketAsset, ...] = (
    MarketAsset("USDCLP", "USD/CLP", "CLP=X"),
    MarketAsset("COPPER", "Cobre", "HG=F"),
    # Yahoo dejo de publicar ^IPSA ("symbol may be delisted"). MXIPSAGC.SN
    # (Bolsa de Santiago) replica el nivel del S&P IPSA, pero su historial
    # diario viene con un solo dato: se usan velas horarias.
    MarketAsset("IPSA", "IPSA", "MXIPSAGC.SN", interval="1h"),
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


def _error_extra(exc: Exception, **extra: object) -> dict[str, object]:
    """Build a log `extra` dict that includes the actual exception message.

    Logging only `type(exc).__name__` hides the real cause (429 rate limit,
    JSON decode error, DNS failure, etc.), which made past failures hard to
    diagnose remotely. This always includes `str(exc)` too.
    """
    return {**extra, "error_type": type(exc).__name__, "error": str(exc) or repr(exc)}


class YFinanceClient:
    """Small yfinance wrapper that tolerates missing tickers and rate limits.

    Descarga ~1 mes de historia en una sola llamada batch por intervalo y de
    ahi deriva tanto la cotizacion (ultimo cierre y variacion diaria) como la
    serie para graficos, sin requests extra a Yahoo.
    """

    def __init__(
        self,
        timeout_seconds: float = 20.0,
        max_retries_per_ticker: int = 2,
        history_period: str = "1mo",
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.max_retries_per_ticker = max_retries_per_ticker
        self.history_period = history_period

    def fetch_quotes(self, assets: tuple[MarketAsset, ...] = DEFAULT_ASSETS) -> list[Quote]:
        if not assets:
            return []

        by_interval: dict[str, list[MarketAsset]] = {}
        for asset in assets:
            by_interval.setdefault(asset.interval, []).append(asset)

        quotes_by_symbol: dict[str, Quote] = {}
        for interval, group in by_interval.items():
            for quote in self._fetch_group(tuple(group), interval):
                quotes_by_symbol[quote.symbol] = quote
        return [quotes_by_symbol[asset.symbol] for asset in assets]

    def _fetch_group(self, assets: tuple[MarketAsset, ...], interval: str) -> list[Quote]:
        tickers = [a.yf_ticker for a in assets]
        try:
            quotes = self._fetch_batch(assets, interval)
            if not any(quote.price is not None for quote in quotes):
                # Batch vacio suele ser bloqueo o rate limit de Yahoo: reintentar
                # ticker por ticker multiplicaria las requests (hasta 36) justo
                # cuando conviene bajar la presion. Se reporta y se sigue.
                logger.warning("No yfinance data returned from batch request", extra={"tickers": tickers})
            return quotes
        except Exception as exc:
            logger.warning(
                "yfinance batch request failed; probando ticker por ticker",
                extra=_error_extra(exc, tickers=tickers),
                exc_info=True,
            )

        return [self._fetch_one(asset) for asset in assets]

    def _download_kwargs(self, interval: str, **overrides: object) -> dict[str, object]:
        kwargs: dict[str, object] = {
            "period": self.history_period,
            "interval": interval,
            "auto_adjust": False,
            "progress": False,
            "timeout": self.timeout_seconds,
        }
        kwargs.update(overrides)
        return kwargs

    def _fetch_batch(self, assets: tuple[MarketAsset, ...], interval: str) -> list[Quote]:
        data = yf.download(
            **self._download_kwargs(
                interval,
                tickers=[asset.yf_ticker for asset in assets],
                threads=True,
                group_by="ticker",
            )
        )
        return [self._quote_from_download(asset, data) for asset in assets]

    def _fetch_one(self, asset: MarketAsset) -> Quote:
        last_exc: Exception | None = None
        for attempt in range(1, self.max_retries_per_ticker + 1):
            try:
                history = yf.download(
                    **self._download_kwargs(asset.interval, tickers=asset.yf_ticker, threads=False)
                )
                return self._quote_from_download(asset, history)
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                logger.warning(
                    "yfinance request failed (intento %d/%d)",
                    attempt,
                    self.max_retries_per_ticker,
                    extra=_error_extra(exc, symbol=asset.symbol, ticker=asset.yf_ticker, attempt=attempt),
                )
                if attempt < self.max_retries_per_ticker:
                    time.sleep(0.5 * attempt + random.uniform(0, 0.5))

        logger.warning(
            "yfinance agoto reintentos para el ticker",
            extra=_error_extra(
                last_exc or RuntimeError("unknown"), symbol=asset.symbol, ticker=asset.yf_ticker
            ),
        )
        return Quote(asset.symbol, asset.name, None, None)

    @staticmethod
    def _quote_from_download(asset: MarketAsset, history, now: datetime | None = None) -> Quote:
        empty = Quote(asset.symbol, asset.name, None, None)
        frame = _extract_ticker_frame(history, asset.yf_ticker)
        if frame is None or "Close" not in frame:
            logger.warning(
                "No yfinance close column returned",
                extra={"symbol": asset.symbol, "ticker": asset.yf_ticker},
            )
            return empty

        try:
            closes = _clean_daily_closes(frame, asset)
        except (ValueError, TypeError) as exc:
            logger.warning(
                "Failed to parse yfinance close prices",
                extra=_error_extra(exc, symbol=asset.symbol, ticker=asset.yf_ticker),
            )
            return empty

        if closes is None or closes.empty:
            logger.warning(
                "No yfinance data returned",
                extra={"symbol": asset.symbol, "ticker": asset.yf_ticker},
            )
            return empty

        last_day = closes.index[-1]
        reference = (now or datetime.now(UTC)).date()
        if (reference - last_day).days > STALE_AFTER_DAYS:
            logger.warning(
                "yfinance data is stale; discarding",
                extra={"symbol": asset.symbol, "ticker": asset.yf_ticker, "last_close": last_day.isoformat()},
            )
            return empty

        price = float(closes.iloc[-1])
        change_pct = None
        if len(closes) >= 2 and float(closes.iloc[-2]) != 0:
            previous = float(closes.iloc[-2])
            change_pct = ((price - previous) / previous) * 100
        series = tuple(float(value) for value in closes.iloc[-HISTORY_POINTS:])
        return Quote(asset.symbol, asset.name, price, change_pct, history=series)


def _extract_ticker_frame(history, ticker: str):
    """Devuelve el DataFrame OHLC de un ticker, venga el batch agrupado o no."""
    if history is None or getattr(history, "empty", True):
        return None

    columns = getattr(history, "columns", None)
    if columns is None:
        return None

    if getattr(columns, "nlevels", 1) > 1:
        level_0 = set(columns.get_level_values(0))
        if ticker in level_0:
            return history[ticker]
        # group_by="column": (campo, ticker)
        if "Close" in level_0:
            fields = {}
            for field_name in ("Open", "High", "Low", "Close"):
                if field_name in level_0 and ticker in history[field_name]:
                    fields[field_name] = history[field_name][ticker]
            if "Close" not in fields:
                return None
            return pd.DataFrame(fields)
        return None

    return history


def _clean_daily_closes(frame, asset: MarketAsset):
    """Cierres diarios validados, indexados por fecha (antiguo -> reciente).

    - Descarta velas con Close fuera de [Low, High] (error de datos de Yahoo).
    - Si demasiadas velas son inconsistentes, descarta la serie completa: es
      preferible "s/d" a publicar un precio no confiable.
    - Para intervalos intradia, se queda con el ultimo cierre de cada dia.
    """
    frame = frame.dropna(subset=["Close"])
    if frame.empty:
        return None

    if "High" in frame and "Low" in frame:
        bounds = frame[["High", "Low"]].notna().all(axis=1)
        close = frame["Close"]
        inconsistent = bounds & (
            (close > frame["High"] * (1 + _OHLC_TOLERANCE)) | (close < frame["Low"] * (1 - _OHLC_TOLERANCE))
        )
        bad = int(inconsistent.sum())
        if bad:
            ratio = bad / len(frame)
            if ratio > MAX_INCONSISTENT_BAR_RATIO:
                logger.warning(
                    "yfinance series inconsistent (close outside high/low); discarding",
                    extra={"symbol": asset.symbol, "ticker": asset.yf_ticker, "bad_bars": bad, "bars": len(frame)},
                )
                return None
            frame = frame[~inconsistent]

    closes = frame["Close"].astype(float)
    closes = closes.groupby([_to_date(ts) for ts in closes.index]).last()
    return closes.sort_index()


def _to_date(ts):
    # Velas intradia vienen con la zona horaria de la bolsa: la fecha local es
    # la que corresponde a la sesion. Velas diarias ya son fechas.
    return ts.date() if hasattr(ts, "date") else ts

