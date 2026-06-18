from datetime import date
from typing import Any

import httpx

from app.config import Settings
from data_sources.bcentral_client import BCentralClient, _parse_float


class FakeHttpClient:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.last_params: dict[str, Any] | None = None

    def get(self, url: str, params: dict[str, Any], timeout: float) -> httpx.Response:
        self.last_params = params
        request = httpx.Request("GET", url)
        return httpx.Response(200, json=self.payload, request=request)


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
