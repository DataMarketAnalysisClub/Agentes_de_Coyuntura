from datetime import UTC, datetime, timedelta

import pytest

from data_sources.rss_news_client import RawNewsItem
from services.source_health import (
    HealthStatus,
    SourceKind,
    check_market_snapshots,
    check_news_sources,
    next_state,
    unavailable_for_readers,
)
from storage.models import MarketSnapshot

NOW = datetime(2026, 9, 29, 12, tzinfo=UTC)
OK, DEGRADED, DOWN = HealthStatus.OK, HealthStatus.DEGRADED, HealthStatus.DOWN


def _raw(source: str, hours_ago: float) -> RawNewsItem:
    return RawNewsItem(NOW - timedelta(hours=hours_ago), source, "t", f"https://x/{source}/{hours_ago}", "")


def _snap(symbol: str, price: float | None) -> MarketSnapshot:
    return MarketSnapshot(NOW, symbol, symbol, price, None, "yfinance")


def test_news_source_without_items_is_down_and_stale_is_degraded() -> None:
    raw = [_raw("FT", 1), _raw("FT", 5), _raw("MarketWatch", 60)]

    checks = {c.source: c for c in check_news_sources(raw, ["FT", "MarketWatch", "Investing.com"], NOW)}

    assert (checks["FT"].status, checks["FT"].items) == (OK, 2)
    assert checks["FT"].newest_at == NOW - timedelta(hours=1)
    assert checks["MarketWatch"].status is DEGRADED
    assert "60 h" in checks["MarketWatch"].detail
    assert checks["Investing.com"].status is DOWN
    assert all(c.kind is SourceKind.NEWS for c in checks.values())


def test_slow_publishers_have_longer_freshness_window() -> None:
    checks = check_news_sources([_raw("Federal Reserve", 100)], ["Federal Reserve"], NOW)

    assert checks[0].status is OK


def test_market_symbol_without_price_is_down_and_macro_kind_is_tagged() -> None:
    checks = {c.source: c for c in check_market_snapshots([_snap("SP500", 7400.0), _snap("TPM", None)], ["SP500", "IPSA", "TPM"], {})}

    assert checks["SP500"].status is OK
    assert checks["IPSA"].status is DOWN  # ni siquiera vino en la lista
    assert (checks["TPM"].status, checks["TPM"].kind) == (DOWN, SourceKind.MACRO)


def test_implausible_price_jump_is_degraded() -> None:
    checks = check_market_snapshots([_snap("USDCLP", 97.0), _snap("GOLD", 2700.0)], ["USDCLP", "GOLD"], {"USDCLP": 970.0, "GOLD": 2650.0})

    by_symbol = {c.source: c for c in checks}
    assert by_symbol["USDCLP"].status is DEGRADED
    assert "salto de 90%" in by_symbol["USDCLP"].detail
    assert by_symbol["GOLD"].status is OK


@pytest.mark.parametrize(
    ("previous_state", "previous_status", "status", "expected"),
    [
        (None, None, DOWN, OK),  # primera corrida mala: aun no alarma
        (OK, OK, DOWN, OK),  # una mala aislada no cambia el estado
        (OK, DOWN, DOWN, DOWN),  # dos seguidas: pasa a caida
        (OK, DEGRADED, DOWN, DOWN),
        (DOWN, DOWN, DEGRADED, DEGRADED),
        (DOWN, DOWN, OK, OK),  # una buena basta para recuperarse
        (DOWN, OK, DOWN, DOWN),  # sin corridas malas seguidas conserva el estado previo
    ],
)
def test_next_state_hysteresis(previous_state, previous_status, status, expected) -> None:
    assert next_state(previous_state, previous_status, status) is expected


def test_unavailable_for_readers_skips_covered_symbols() -> None:
    checks = check_market_snapshots([_snap("SP500", 1.0)], ["SP500", "IPSA", "USDPEN"], {})
    checks += check_news_sources([], ["Investing.com"], NOW)

    assert unavailable_for_readers(checks, covered={"IPSA"}) == ["USDPEN", "Investing.com"]
