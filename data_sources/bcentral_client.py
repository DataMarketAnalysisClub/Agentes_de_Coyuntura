import json
import logging
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol

import httpx

from app.config import Settings, get_settings
from data_sources.yfinance_client import Quote

logger = logging.getLogger(__name__)


BCENTRAL_API_URL = "https://si3.bcentral.cl/SieteRestWS/SieteRestWS.ashx"
# Mismos criterios que yfinance: ~1 mes habil de historia para graficos y un
# dato diario con mas de 7 dias de antiguedad se considera vencido.
FX_HISTORY_POINTS = 22
FX_LOOKBACK_DAYS = 45
FX_STALE_AFTER_DAYS = 7


class HttpClient(Protocol):
    def get(self, url: str, params: dict[str, Any], timeout: float) -> httpx.Response: ...


@dataclass(frozen=True)
class BCentralObservation:
    series_id: str
    observed_at: date | None
    value: float


class BCentralClient:
    """Banco Central de Chile SieteRestWS client."""

    def __init__(self, settings: Settings | None = None, http_client: HttpClient | None = None) -> None:
        self.settings = settings or get_settings()
        # Sin cliente inyectado, cada request abre y cierra su propio
        # httpx.Client (antes se creaba uno que nunca se cerraba). Asi las
        # series se pueden pedir en paralelo desde varios hilos.
        self.http_client = http_client

    def fetch_policy_rate(self) -> float | None:
        observation = self.fetch_latest_observation(self.settings.bcentral_tpm_series, lookback_days=120)
        return observation.value if observation else None

    def fetch_inflation(self) -> float | None:
        observation = self.fetch_latest_observation(self.settings.bcentral_ipc_series, lookback_days=900)
        return observation.value if observation else None

    def fetch_unemployment(self) -> float | None:
        # Mensual (trimestre movil INE) y publicada con ~1 mes de rezago.
        observation = self.fetch_latest_observation(self.settings.bcentral_unemployment_series, lookback_days=400)
        return observation.value if observation else None

    def fetch_fx_quote(self, series_id: str, symbol: str, name: str) -> Quote | None:
        """Tipo de cambio diario como `Quote`: ultimo valor, variacion y ~1 mes de historia."""
        observations = self.fetch_observations(series_id, lookback_days=FX_LOOKBACK_DAYS)
        if not observations:
            return None
        last = observations[-1]
        today = datetime.now(UTC).date()
        if last.observed_at is None or (today - last.observed_at).days > FX_STALE_AFTER_DAYS:
            logger.warning(
                "BCentral FX series is stale; skipping",
                extra={"series_id": series_id, "observed_at": str(last.observed_at)},
            )
            return None
        change_pct = None
        if len(observations) >= 2 and observations[-2].value:
            change_pct = round((last.value / observations[-2].value - 1) * 100, 4)
        history = tuple(item.value for item in observations[-FX_HISTORY_POINTS:])
        return Quote(symbol, name, last.value, change_pct, "bcentral", history=history)

    def fetch_latest_observation(self, series_id: str, lookback_days: int = 365) -> BCentralObservation | None:
        observations = self.fetch_observations(series_id, lookback_days)
        return observations[-1] if observations else None

    def fetch_observations(self, series_id: str, lookback_days: int = 365) -> list[BCentralObservation]:
        """Observaciones validas de la serie, de la mas antigua a la mas reciente."""
        if not self.settings.bcentral_user or not self.settings.bcentral_password:
            logger.warning("BCentral credentials missing", extra={"series_id": series_id})
            return []
        if not series_id:
            logger.warning("BCentral series id missing")
            return []

        today = datetime.now(UTC).date()
        first_date = today - timedelta(days=lookback_days)
        params = {
            "user": self.settings.bcentral_user,
            "pass": self.settings.bcentral_password,
            "function": "GetSeries",
            "timeseries": series_id,
            "firstdate": first_date.isoformat(),
            "lastdate": today.isoformat(),
        }

        try:
            response = self._get(params)
            response.raise_for_status()
            payload = json.loads(response.text)
        except Exception as exc:
            logger.warning(
                "Failed to fetch BCentral series",
                extra={"series_id": series_id, "error_type": type(exc).__name__, "error": self._safe_error(exc)},
            )
            return []

        return self._observations_from_payload(series_id, payload)

    def _get(self, params: dict[str, Any]) -> httpx.Response:
        timeout = self.settings.bcentral_timeout_seconds
        if self.http_client is not None:
            return self.http_client.get(BCENTRAL_API_URL, params=params, timeout=timeout)
        with httpx.Client() as client:
            return client.get(BCENTRAL_API_URL, params=params, timeout=timeout)

    def _safe_error(self, exc: Exception) -> str:
        """Mensaje de la excepcion sin credenciales.

        Los errores HTTP de httpx incluyen la URL completa, con usuario y
        contrasena en la query string: nunca deben llegar a los logs.
        """
        if isinstance(exc, httpx.HTTPStatusError):
            return f"HTTP {exc.response.status_code}"
        message = str(exc) or repr(exc)
        for secret in (self.settings.bcentral_password, self.settings.bcentral_user):
            if secret:
                message = message.replace(secret, "***")
        return message

    def _observations_from_payload(self, series_id: str, payload: dict[str, Any]) -> list[BCentralObservation]:
        if str(payload.get("Codigo", "0")) not in {"0", "OK", "None"}:
            logger.warning(
                "BCentral API returned non-success code",
                extra={
                    "series_id": series_id,
                    "code": payload.get("Codigo"),
                    "description": self._safe_error(Exception(str(payload.get("Descripcion", "")))),
                },
            )
            return []

        observations = (payload.get("Series") or {}).get("Obs") or []
        parsed: list[BCentralObservation] = []
        for observation in observations:
            value = _parse_float(observation.get("value"))
            if value is None:
                continue
            observed_at = _parse_date(observation.get("indexDateString"))
            parsed.append(BCentralObservation(series_id, observed_at, value))

        if not parsed:
            logger.warning("BCentral series returned no usable observations", extra={"series_id": series_id})
            return []
        return sorted(parsed, key=lambda item: item.observed_at or date.min)


def _parse_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        normalized = str(value).strip()
        if "," in normalized and "." in normalized:
            if normalized.rfind(",") > normalized.rfind("."):
                normalized = normalized.replace(".", "").replace(",", ".")
            else:
                normalized = normalized.replace(",", "")
        elif "," in normalized:
            normalized = normalized.replace(",", ".")
        parsed = float(normalized)
    except ValueError:
        return None
    # La API marca los dias sin dato (feriados, fines de semana) con "NaN".
    return parsed if math.isfinite(parsed) else None


def _parse_date(value: object) -> date | None:
    if not value:
        return None
    raw = str(value).strip()
    for date_format in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw, date_format).date()
        except ValueError:
            continue
    return None
