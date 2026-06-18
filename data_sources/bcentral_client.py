import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


BCENTRAL_API_URL = "https://si3.bcentral.cl/SieteRestWS/SieteRestWS.ashx"


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
        self.http_client = http_client or httpx.Client()

    def fetch_policy_rate(self) -> float | None:
        observation = self.fetch_latest_observation(self.settings.bcentral_tpm_series, lookback_days=120)
        return observation.value if observation else None

    def fetch_inflation(self) -> float | None:
        observation = self.fetch_latest_observation(self.settings.bcentral_ipc_series, lookback_days=900)
        return observation.value if observation else None

    def fetch_latest_observation(self, series_id: str, lookback_days: int = 365) -> BCentralObservation | None:
        if not self.settings.bcentral_user or not self.settings.bcentral_password:
            logger.warning("BCentral credentials missing", extra={"series_id": series_id})
            return None
        if not series_id:
            logger.warning("BCentral series id missing")
            return None

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
            response = self.http_client.get(
                BCENTRAL_API_URL,
                params=params,
                timeout=self.settings.bcentral_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            logger.warning(
                "Failed to fetch BCentral series",
                extra={"series_id": series_id, "error_type": type(exc).__name__},
            )
            return None

        return self._latest_from_payload(series_id, payload)

    def _latest_from_payload(self, series_id: str, payload: dict[str, Any]) -> BCentralObservation | None:
        if str(payload.get("Codigo", "0")) not in {"0", "OK", "None"}:
            logger.warning("BCentral API returned non-success code", extra={"series_id": series_id})
            return None

        observations = payload.get("Series", {}).get("Obs", [])
        parsed: list[BCentralObservation] = []
        for observation in observations:
            value = _parse_float(observation.get("value"))
            if value is None:
                continue
            observed_at = _parse_date(observation.get("indexDateString"))
            parsed.append(BCentralObservation(series_id, observed_at, value))

        if not parsed:
            logger.warning("BCentral series returned no usable observations", extra={"series_id": series_id})
            return None
        return sorted(parsed, key=lambda item: item.observed_at or date.min)[-1]


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
        return float(normalized)
    except ValueError:
        return None


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
