"""Suscriptores del mailing (MySQL).

La SQLite sigue guardando snapshots, noticias y auditoria de envios; aqui solo
viven los correos inscritos y su historial de altas y bajas. Datos personales
minimos: correo, estado y fechas (sin IP ni nombre).

El SQL usa placeholders `%s` (PyMySQL). Los tests corren el mismo SQL sobre
SQLite con un adaptador (ver `tests/test_subscribers_repository.py`), asi que
las consultas evitan sintaxis exclusiva de MySQL; el DDL de `MYSQL_SCHEMA` es
la excepcion.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from app.config import Settings, get_settings


class SubscriberStatus(StrEnum):
    PENDING = "pending"
    ACTIVE = "active"
    UNSUBSCRIBED = "unsubscribed"


class SubscriberEvent(StrEnum):
    SUBSCRIBE_REQUESTED = "subscribe_requested"
    CONFIRMATION_SENT = "confirmation_sent"
    CONFIRMED = "confirmed"
    UNSUBSCRIBED = "unsubscribed"
    ADDED_BY_ADMIN = "added_by_admin"


# Utf8mb4 para el correo (comparacion sin mayusculas); el token en ascii_bin
# porque distingue mayusculas (secrets.token_urlsafe).
MYSQL_SCHEMA = (
    """
    CREATE TABLE IF NOT EXISTS subscribers (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        email VARCHAR(254) NOT NULL,
        status ENUM('pending', 'active', 'unsubscribed') NOT NULL DEFAULT 'pending',
        token VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
        source VARCHAR(32) NOT NULL DEFAULT 'web',
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        confirmation_sent_at DATETIME NULL,
        confirmed_at DATETIME NULL,
        unsubscribed_at DATETIME NULL,
        UNIQUE KEY uq_subscribers_email (email),
        UNIQUE KEY uq_subscribers_token (token),
        KEY idx_subscribers_status (status)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS subscriber_events (
        id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
        subscriber_id BIGINT UNSIGNED NOT NULL,
        event VARCHAR(32) NOT NULL,
        occurred_at DATETIME NOT NULL,
        detail VARCHAR(255) NOT NULL DEFAULT '',
        KEY idx_subscriber_events_subscriber (subscriber_id),
        KEY idx_subscriber_events_event (event, occurred_at),
        CONSTRAINT fk_subscriber_events_subscriber FOREIGN KEY (subscriber_id)
            REFERENCES subscribers (id) ON DELETE CASCADE
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
    """,
)

_COLUMNS = (
    "id, email, status, token, source, created_at, updated_at,"
    " confirmation_sent_at, confirmed_at, unsubscribed_at"
)


class DuplicateSubscriberError(Exception):
    """El correo (o el token) ya existe."""


@dataclass(frozen=True)
class Subscriber:
    id: int
    email: str
    status: SubscriberStatus
    token: str
    source: str
    created_at: datetime
    updated_at: datetime
    confirmation_sent_at: datetime | None = None
    confirmed_at: datetime | None = None
    unsubscribed_at: datetime | None = None


def _integrity_errors() -> tuple[type[Exception], ...]:
    errors: list[type[Exception]] = [sqlite3.IntegrityError]
    try:
        import pymysql

        errors.append(pymysql.err.IntegrityError)
    except ImportError:  # pragma: no cover - pymysql esta en requirements
        pass
    return tuple(errors)


def _as_datetime(value: Any) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _row_to_subscriber(row: dict[str, Any]) -> Subscriber:
    return Subscriber(
        id=int(row["id"]),
        email=row["email"],
        status=SubscriberStatus(row["status"]),
        token=row["token"],
        source=row["source"],
        created_at=_as_datetime(row["created_at"]),
        updated_at=_as_datetime(row["updated_at"]),
        confirmation_sent_at=_as_datetime(row["confirmation_sent_at"]),
        confirmed_at=_as_datetime(row["confirmed_at"]),
        unsubscribed_at=_as_datetime(row["unsubscribed_at"]),
    )


def mysql_connection_factory(settings: Settings | None = None) -> Callable[[], Any]:
    """Conexiones PyMySQL con filas como dict; las fechas se guardan en UTC."""
    current = settings or get_settings()

    def connect():
        import pymysql

        return pymysql.connect(
            host=current.mysql_host,
            port=current.mysql_port,
            user=current.mysql_user,
            password=current.mysql_password,
            database=current.mysql_database,
            charset="utf8mb4",
            autocommit=False,
            connect_timeout=10,
            read_timeout=30,
            write_timeout=30,
            cursorclass=pymysql.cursors.DictCursor,
            init_command="SET time_zone = '+00:00'",
        )

    return connect


class SubscriberRepository:
    """Acceso a `subscribers` y `subscriber_events`.

    Cada metodo abre su conexion y confirma su transaccion: el servicio web es
    multihilo y el job de envio corre en otro contenedor.
    Las fechas son UTC sin zona (`DATETIME`).
    """

    def __init__(self, connect: Callable[[], Any]) -> None:
        self._connect = connect

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> SubscriberRepository:
        return cls(mysql_connection_factory(settings))

    @contextmanager
    def _cursor(self) -> Iterator[Any]:
        connection = self._connect()
        try:
            cursor = connection.cursor()
            try:
                yield cursor
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                cursor.close()
        finally:
            connection.close()

    def init_schema(self) -> None:
        with self._cursor() as cursor:
            for statement in MYSQL_SCHEMA:
                cursor.execute(statement)

    def ping(self) -> None:
        with self._cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()

    # --- Lecturas ---------------------------------------------------------

    def get_by_email(self, email: str) -> Subscriber | None:
        return self._fetch_one(f"SELECT {_COLUMNS} FROM subscribers WHERE email = %s", (email,))

    def get_by_token(self, token: str) -> Subscriber | None:
        return self._fetch_one(f"SELECT {_COLUMNS} FROM subscribers WHERE token = %s", (token,))

    def find(self, status: SubscriberStatus | None = None) -> list[Subscriber]:
        with self._cursor() as cursor:
            if status is None:
                cursor.execute(f"SELECT {_COLUMNS} FROM subscribers ORDER BY id")
            else:
                cursor.execute(
                    f"SELECT {_COLUMNS} FROM subscribers WHERE status = %s ORDER BY id", (str(status),)
                )
            return [_row_to_subscriber(row) for row in cursor.fetchall()]

    def active(self) -> list[Subscriber]:
        return self.find(SubscriberStatus.ACTIVE)

    def counts_by_status(self) -> dict[str, int]:
        with self._cursor() as cursor:
            cursor.execute("SELECT status, COUNT(*) AS total FROM subscribers GROUP BY status")
            counts = {str(status): 0 for status in SubscriberStatus}
            counts.update({row["status"]: int(row["total"]) for row in cursor.fetchall()})
            return counts

    def count_events_since(self, event: SubscriberEvent, since: datetime) -> int:
        with self._cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS total FROM subscriber_events WHERE event = %s AND occurred_at >= %s",
                (str(event), since),
            )
            return int(cursor.fetchone()["total"])

    # --- Escrituras -------------------------------------------------------

    def create(
        self,
        email: str,
        token: str,
        source: str,
        now: datetime,
        status: SubscriberStatus = SubscriberStatus.PENDING,
    ) -> Subscriber:
        confirmed_at = now if status is SubscriberStatus.ACTIVE else None
        try:
            with self._cursor() as cursor:
                cursor.execute(
                    "INSERT INTO subscribers (email, status, token, source, created_at, updated_at, confirmed_at)"
                    " VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (email, str(status), token, source, now, now, confirmed_at),
                )
        except _integrity_errors() as exc:
            raise DuplicateSubscriberError(email) from exc
        created = self.get_by_email(email)
        assert created is not None
        return created

    def restart_pending(self, subscriber_id: int, token: str, source: str, now: datetime) -> None:
        """Vuelve a `pending` con token nuevo (reinscripcion o link vencido)."""
        self._execute(
            "UPDATE subscribers SET status = %s, token = %s, source = %s, updated_at = %s,"
            " confirmation_sent_at = NULL, confirmed_at = NULL WHERE id = %s",
            (str(SubscriberStatus.PENDING), token, source, now, subscriber_id),
        )

    def mark_confirmation_sent(self, subscriber_id: int, now: datetime) -> None:
        self._execute(
            "UPDATE subscribers SET confirmation_sent_at = %s, updated_at = %s WHERE id = %s",
            (now, now, subscriber_id),
        )

    def activate(self, subscriber_id: int, now: datetime) -> None:
        self._execute(
            "UPDATE subscribers SET status = %s, confirmed_at = %s, unsubscribed_at = NULL,"
            " updated_at = %s WHERE id = %s",
            (str(SubscriberStatus.ACTIVE), now, now, subscriber_id),
        )

    def unsubscribe(self, subscriber_id: int, now: datetime) -> None:
        self._execute(
            "UPDATE subscribers SET status = %s, unsubscribed_at = %s, updated_at = %s WHERE id = %s",
            (str(SubscriberStatus.UNSUBSCRIBED), now, now, subscriber_id),
        )

    def delete(self, subscriber_id: int) -> None:
        """Borra al suscriptor y su historial (derecho de supresion)."""
        with self._cursor() as cursor:
            cursor.execute("DELETE FROM subscriber_events WHERE subscriber_id = %s", (subscriber_id,))
            cursor.execute("DELETE FROM subscribers WHERE id = %s", (subscriber_id,))

    def add_event(self, subscriber_id: int, event: SubscriberEvent, now: datetime, detail: str = "") -> None:
        self._execute(
            "INSERT INTO subscriber_events (subscriber_id, event, occurred_at, detail) VALUES (%s, %s, %s, %s)",
            (subscriber_id, str(event), now, detail[:255]),
        )

    # --- Helpers ----------------------------------------------------------

    def _fetch_one(self, sql: str, params: tuple) -> Subscriber | None:
        with self._cursor() as cursor:
            cursor.execute(sql, params)
            row = cursor.fetchone()
        return _row_to_subscriber(row) if row else None

    def _execute(self, sql: str, params: tuple) -> None:
        with self._cursor() as cursor:
            cursor.execute(sql, params)
