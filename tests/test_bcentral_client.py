from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from app.config import Settings
from data_sources.bcentral_client import BCentralClient, _parse_float


class FakeHttpClient:
    def __init__(self, payload: dict[str, Any], status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code
        self.last_params: dict[str, Any] | None = None

    def get(self, url: str, params: dict[str, Any], timeout: float) -> httpx.Response:
        self.last_params = params
        request = httpx.Request("GET", url, params=params)
        return httpx.Response(self.status_code, json=self.payload, request=request)


SETTINGS = Settings(bcentral_user="user@example.com", bcentral_password="secret")


def _daily_obs(values: list[str], end: date) -> list[dict[str, str]]:
    start = end - timedelta(days=len(values) - 1)
    return [
        {"indexDateString": (start + timedelta(days=i)).strftime("%d-%m-%Y"), "value": value}
        for i, value in enumerate(values)
    ]


def test_fetch_latest_observation_parses_bcentral_payload() -> None:
    payload = {
        "Codigo": 0,
        "Series": {
            "Obs": [
                {"indexDateString": "2026-01-01", "value": "5.25"},
                {"indexDateString": "2026-01-02", "value": "5,50"},
            ]
        },
    }
    fake_http = FakeHttpClient(payload)
    settings = Settings(bcentral_user="user@example.com", bcentral_password="secret")
    client = BCentralClient(settings, fake_http)

    observation = client.fetch_latest_observation("SERIES", lookback_days=10)

    assert observation is not None
    assert observation.series_id == "SERIES"
    assert observation.observed_at == date(2026, 1, 2)
    assert observation.value == 5.5
    assert fake_http.last_params is not None
    assert fake_http.last_params["timeseries"] == "SERIES"


def test_fetch_latest_observation_returns_none_without_credentials() -> None:
    fake_http = FakeHttpClient({"Codigo": 0, "Series": {"Obs": []}})
    client = BCentralClient(Settings(), fake_http)

    assert client.fetch_latest_observation("SERIES") is None
    assert fake_http.last_params is None


def test_parse_float_accepts_common_bcentral_formats() -> None:
    assert _parse_float("5.50") == 5.5
    assert _parse_float("5,50") == 5.5
    assert _parse_float("1.234,56") == 1234.56
    assert _parse_float("1,234.56") == 1234.56


def test_parse_float_rejects_nan_markers() -> None:
    assert _parse_float("NaN") is None
    assert _parse_float("inf") is None


def test_fetch_fx_quote_builds_quote_with_history_and_skips_nan() -> None:
    today = datetime.now(UTC).date()
    payload = {"Codigo": 0, "Series": {"Obs": _daily_obs(["3.70", "NaN", "3.75", "3.60"], today)}}
    client = BCentralClient(SETTINGS, FakeHttpClient(payload))

    quote = client.fetch_fx_quote("F072.PEN.USD.N.O.D", "USDPEN", "USD/PEN")

    assert quote is not None
    assert (quote.symbol, quote.name, quote.source) == ("USDPEN", "USD/PEN", "bcentral")
    assert quote.price == 3.60
    assert quote.history == (3.70, 3.75, 3.60)
    assert quote.change_pct == round((3.60 / 3.75 - 1) * 100, 4)


def test_fetch_fx_quote_discards_stale_series() -> None:
    old = datetime.now(UTC).date() - timedelta(days=20)
    payload = {"Codigo": 0, "Series": {"Obs": _daily_obs(["3.70", "3.71"], old)}}
    client = BCentralClient(SETTINGS, FakeHttpClient(payload))

    assert client.fetch_fx_quote("F072.PEN.USD.N.O.D", "USDPEN", "USD/PEN") is None


def test_fetch_unemployment_uses_configured_series() -> None:
    payload = {"Codigo": 0, "Series": {"Obs": [{"indexDateString": "01-07-2026", "value": "8.7"}]}}
    fake_http = FakeHttpClient(payload)
    client = BCentralClient(SETTINGS, fake_http)

    assert client.fetch_unemployment() == 8.7
    assert fake_http.last_params is not None
    assert fake_http.last_params["timeseries"] == "F049.DES.TAS.INE9.10.M"


def test_http_errors_are_logged_without_credentials(caplog) -> None:
    client = BCentralClient(SETTINGS, FakeHttpClient({}, status_code=500))

    with caplog.at_level("WARNING"):
        assert client.fetch_latest_observation("SERIES") is None

    record = next(r for r in caplog.records if r.getMessage() == "Failed to fetch BCentral series")
    assert record.error == "HTTP 500"
    assert "secret" not in str(record.__dict__)


def test_non_success_code_is_logged_with_description(caplog) -> None:
    payload = {"Codigo": -5, "Descripcion": "Invalid username or password"}
    client = BCentralClient(SETTINGS, FakeHttpClient(payload))

    with caplog.at_level("WARNING"):
        assert client.fetch_latest_observation("SERIES") is None

    record = next(r for r in caplog.records if r.getMessage() == "BCentral API returned non-success code")
    assert record.code == -5
    assert record.description == "Invalid username or password"
