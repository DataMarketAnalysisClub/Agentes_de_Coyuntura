from datetime import UTC, datetime, timedelta

import pytest

import storage.database as database
from app.config import Settings
from services.source_health import HealthStatus, SourceCheck, SourceKind
from services.source_health_report import format_health_table, record_health
from storage.models import MarketSnapshot
from storage.repositories import MarketSnapshotRepository, SourceHealthRepository

NOW = datetime(2026, 9, 29, 12, tzinfo=UTC)
OK, DOWN = HealthStatus.OK, HealthStatus.DOWN


@pytest.fixture(autouse=True)
def temp_db(tmp_path, monkeypatch):
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}")
    monkeypatch.setattr(database, "get_settings", lambda: settings)
    database.init_db(settings)


def _check(source: str, status: HealthStatus, detail: str = "") -> SourceCheck:
    return SourceCheck(source, SourceKind.NEWS, status, 0 if status is DOWN else 5, detail=detail)


def _run(hours: int, *checks: SourceCheck):
    return record_health(list(checks), NOW + timedelta(hours=hours))


def test_single_bad_run_does_not_transition_but_two_do_and_recovery_is_reported() -> None:
    assert _run(0, _check("FT", OK)) == []
    assert _run(1, _check("FT", DOWN, "sin notas")) == []

    transitions = _run(2, _check("FT", DOWN, "sin notas"))
    assert [(t.source, t.previous, t.current, t.detail) for t in transitions] == [("FT", OK, DOWN, "sin notas")]
    assert _run(3, _check("FT", DOWN)) == []  # sigue caida: sin aviso repetido

    recovered = _run(4, _check("FT", OK))
    assert [(t.previous, t.current) for t in recovered] == [(DOWN, OK)]


def test_state_tracks_since_and_last_ok() -> None:
    _run(0, _check("FT", OK))
    _run(1, _check("FT", DOWN))
    _run(2, _check("FT", DOWN, "sin notas"))

    state = SourceHealthRepository().states()["FT"]
    assert (state.state, state.last_status, state.detail) == ("caida", "caida", "sin notas")
    assert state.since == NOW + timedelta(hours=2)
    assert state.last_ok_at == NOW
    assert "caida" in format_health_table({"FT": state})


def test_old_health_rows_are_pruned() -> None:
    _run(0, _check("FT", OK))
    _run(24 * 31, _check("FT", OK))

    with database.get_connection() as connection:
        rows = connection.execute("SELECT run_at FROM source_health").fetchall()
    assert len(rows) == 1


def test_last_valid_prices_skips_nulls_and_keeps_latest() -> None:
    repo = MarketSnapshotRepository()
    repo.save_many([MarketSnapshot(NOW - timedelta(days=2), "SP500", "S&P 500", 7300.0, 0.1, "yfinance")])
    repo.save_many([MarketSnapshot(NOW - timedelta(days=1), "SP500", "S&P 500", 7400.0, 0.2, "yfinance")])
    repo.save_many([MarketSnapshot(NOW, "SP500", "S&P 500", None, None, "yfinance")])

    prices = repo.last_valid_prices(NOW - timedelta(days=5))

    assert prices == {"SP500": (7400.0, NOW - timedelta(days=1))}


def test_empty_table_message() -> None:
    assert "Sin registros" in format_health_table({})
