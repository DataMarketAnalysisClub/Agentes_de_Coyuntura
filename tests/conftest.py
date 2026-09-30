"""Pytest configuration: prevent accidental Ollama Cloud calls in tests.

The project loads settings from `.env`, which can have AI_ENABLED=true and
a real OLLAMA_API_KEY. Tests should never hit the real API. This conftest
patches OllamaCloudClient in all AI modules so any test that creates a client
gets a mock that is disabled and returns dry-run stubs.

Tests that want to exercise the Ollama path (e.g. test_ollama_client.py) can
mark themselves with @pytest.mark.allow_ollama_calls.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

_OLLAMA_TARGETS = (
    "services.ai.macro_router.OllamaCloudClient",
    "services.ai.topic_router.OllamaCloudClient",
    "services.ai.pipeline.OllamaCloudClient",
    "services.ai.editorial_writer.OllamaCloudClient",
    "services.ai.smoke_test.OllamaCloudClient",
)


@pytest.fixture(autouse=True)
def _disable_ollama_calls(request):
    if "allow_ollama_calls" in request.keywords:
        yield
        return
    from app.config import Settings

    settings = Settings(
        ai_enabled=False,
        ai_dry_run=True,
        ollama_api_key="test-key",
        ollama_model="gpt-oss:120b",
        ollama_base_url="https://ollama.com",
        ollama_timeout_seconds=5.0,
        ollama_temperature=0.2,
        ollama_max_retries=1,
    )
    patches = [patch(target) for target in _OLLAMA_TARGETS]
    mocks = [p.start() for p in patches]
    for mock in mocks:
        mock.return_value.settings = settings
        mock.return_value.is_enabled.return_value = False
        mock.return_value.is_dry_run.return_value = True
    try:
        yield
    finally:
        for p in patches:
            p.stop()


@pytest.fixture(autouse=True)
def _no_front_contract_lookup(request, monkeypatch):
    """Los tests no consultan a Yahoo por el contrato vigente de los futuros.

    Sin contrato resuelto el cliente usa el ticker continuo, como antes.
    Los tests que prueban la resolucion se marcan con
    @pytest.mark.allow_front_contract_lookup.
    """
    if "allow_front_contract_lookup" in request.keywords:
        return
    import data_sources.yfinance_client as module

    monkeypatch.setattr(module, "_front_contract_symbol", lambda ticker: None)


def pytest_configure(config):
    config.addinivalue_line("markers", "allow_ollama_calls: permite usar el cliente Ollama real en el test")
    config.addinivalue_line(
        "markers", "allow_front_contract_lookup: no parchea la resolucion del contrato vigente de futuros"
    )


@pytest.fixture(autouse=True)
def _ignore_local_env_file(monkeypatch):
    """Los tests no leen el `.env` local (credenciales reales, SMTP, IA).

    Sin esto, Settings() tomaba las credenciales del BCCh del `.env` del
    desarrollador: los tests dejaban de ser deterministas y un assert fallido
    podia imprimir la contrasena en la salida de pytest.
    """
    from app.config import Settings, get_settings

    monkeypatch.setitem(Settings.model_config, "env_file", None)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


# --- Suscriptores: el SQL de storage/subscribers.py sobre SQLite -------------

_SQLITE_SUBSCRIBER_SCHEMA = """
CREATE TABLE subscribers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'unsubscribed')),
    token TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL DEFAULT 'web',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    confirmation_sent_at TEXT,
    confirmed_at TEXT,
    unsubscribed_at TEXT
);
CREATE TABLE subscriber_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subscriber_id INTEGER NOT NULL REFERENCES subscribers (id) ON DELETE CASCADE,
    event TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT ''
);
"""


class _SqliteCursor:
    """Cursor estilo PyMySQL (%s, filas dict) sobre sqlite3."""

    def __init__(self, cursor) -> None:
        self._cursor = cursor

    def execute(self, sql, params=()):
        from datetime import datetime

        values = tuple(value.isoformat(sep=" ") if isinstance(value, datetime) else value for value in params)
        return self._cursor.execute(sql.replace("%s", "?"), values)

    def fetchone(self):
        row = self._cursor.fetchone()
        return dict(row) if row is not None else None

    def fetchall(self):
        return [dict(row) for row in self._cursor.fetchall()]

    def close(self) -> None:
        self._cursor.close()


class _SqliteConnection:
    def __init__(self, path) -> None:
        import sqlite3

        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")

    def cursor(self):
        return _SqliteCursor(self._connection.cursor())

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()


@pytest.fixture
def subscriber_repository(tmp_path):
    """SubscriberRepository real sobre un archivo SQLite temporal."""
    import sqlite3

    from storage.subscribers import SubscriberRepository

    path = tmp_path / "subscribers.db"
    with sqlite3.connect(path) as connection:
        connection.executescript(_SQLITE_SUBSCRIBER_SCHEMA)
    return SubscriberRepository(lambda: _SqliteConnection(path))
