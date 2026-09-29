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


class FakeSender:
    def __init__(self) -> None:
        self.calls = []

    def send(self, subject, text_body, html_body, enabled, recipients=None) -> bool:
        self.calls.append((subject, text_body, enabled, recipients))
        return True


def test_notify_transitions_sends_one_email_to_ops_only() -> None:
    from services.source_health_report import Transition, notify_transitions

    settings = Settings(ops_email_to="ops@example.com, dev@example.com", email_enabled=True)
    transitions = [
        Transition("Investing.com", SourceKind.NEWS, OK, DOWN, "sin notas"),
        Transition("IPSA", SourceKind.MARKET, DOWN, OK),
    ]
    checks = [_check("Investing.com", DOWN, "sin notas"), _check("IPSA", OK)]
    sender = FakeSender()

    assert notify_transitions(transitions, checks, settings, sender)

    [(subject, body, enabled, recipients)] = sender.calls
    assert subject == "DMAC | Salud de fuentes: 1 con problemas, 1 recuperada(s)"
    assert "* Investing.com (noticias): caida. sin notas" in body
    assert "2. Fuentes recuperadas\n* IPSA (mercado)" in body
    assert enabled is True
    assert recipients == ["ops@example.com", "dev@example.com"]


def test_notify_transitions_without_ops_recipients_or_changes_sends_nothing() -> None:
    from services.source_health_report import Transition, notify_transitions

    sender = FakeSender()
    transition = Transition("FT", SourceKind.NEWS, OK, DOWN)

    assert not notify_transitions([transition], [], Settings(ops_email_to=""), sender)
    assert not notify_transitions([], [], Settings(ops_email_to="ops@example.com"), sender)
    assert sender.calls == []


def test_feed_down_two_runs_in_a_row_triggers_exactly_one_alert(monkeypatch) -> None:
    import jobs.common as common
    from data_sources.rss_news_client import RawNewsItem

    notified = []
    monkeypatch.setattr(common, "notify_transitions", lambda transitions, checks: notified.append(transitions))
    monkeypatch.setattr(common, "expected_market_symbols", lambda: ["SP500"])
    snapshots = [MarketSnapshot(datetime.now(UTC), "SP500", "S&P 500", 7400.0, 0.1, "yfinance")]
    raw = [RawNewsItem(datetime.now(UTC), "FT", "t", "https://x", "")]

    for _ in range(3):
        checks = common._evaluate_health(raw, ["FT", "Investing.com"], snapshots)

    assert {c.source: str(c.status) for c in checks} == {"FT": "ok", "Investing.com": "caida", "SP500": "ok"}
    alerts = [transitions for transitions in notified if transitions]
    assert len(alerts) == 1
    assert [(t.source, str(t.current)) for t in alerts[0]] == [("Investing.com", "caida")]
