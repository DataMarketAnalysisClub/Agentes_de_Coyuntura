from dataclasses import dataclass
from datetime import datetime, timedelta

from storage.database import get_connection
from storage.models import Alert, Brief, MarketSnapshot, NewsItem, SentEmail


def _iso(value: datetime) -> str:
    return value.isoformat()


class MarketSnapshotRepository:
    def save_many(self, snapshots: list[MarketSnapshot]) -> None:
        if not snapshots:
            return
        with get_connection() as connection:
            connection.executemany(
                """
                INSERT INTO market_snapshots (timestamp, symbol, name, price, change_pct, source)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (_iso(item.timestamp), item.symbol, item.name, item.price, item.change_pct, item.source)
                    for item in snapshots
                ],
            )


    def last_valid_prices(self, since: datetime) -> dict[str, tuple[float, datetime]]:
        """Ultimo precio no nulo por simbolo desde `since`, con su timestamp."""
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT symbol, price, timestamp FROM market_snapshots
                WHERE price IS NOT NULL AND timestamp >= ?
                ORDER BY timestamp
                """,
                (_iso(since),),
            ).fetchall()
        return {row["symbol"]: (row["price"], datetime.fromisoformat(row["timestamp"])) for row in rows}


class NewsRepository:
    def save_many(self, items: list[NewsItem]) -> int:
        inserted = 0
        with get_connection() as connection:
            for item in items:
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO news_items
                    (timestamp, source, title, url, summary, region, topic, impact_score)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _iso(item.timestamp),
                        item.source,
                        item.title,
                        item.url,
                        item.summary,
                        item.region,
                        item.topic,
                        item.impact_score,
                    ),
                )
                inserted += cursor.rowcount
        return inserted

    def recent_mentions(self, now: datetime, lookback_hours: int) -> list[NewsItem]:
        since = now - timedelta(hours=lookback_hours)
        with get_connection() as connection:
            rows = connection.execute(
                """
                SELECT timestamp, source, title, url, summary, region, topic, impact_score
                FROM news_mentions
                WHERE mentioned_at >= ?
                ORDER BY mentioned_at DESC
                """,
                (_iso(since),),
            ).fetchall()
        return [
            NewsItem(
                timestamp=datetime.fromisoformat(row["timestamp"]),
                source=row["source"],
                title=row["title"],
                url=row["url"],
                summary=row["summary"] or "",
                region=row["region"] or "Global",
                topic=row["topic"] or "macro general",
                impact_score=row["impact_score"] or 0,
            )
            for row in rows
        ]

    def save_mentions(self, items: list[NewsItem], mentioned_at: datetime) -> None:
        if not items:
            return
        with get_connection() as connection:
            connection.executemany(
                """
                INSERT INTO news_mentions
                (mentioned_at, timestamp, source, title, url, summary, region, topic, impact_score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        _iso(mentioned_at),
                        _iso(item.timestamp),
                        item.source,
                        item.title,
                        item.url,
                        item.summary,
                        item.region,
                        item.topic,
                        item.impact_score,
                    )
                    for item in items
                ],
            )


class BriefRepository:
    def save(self, brief: Brief) -> None:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO briefs (timestamp, type, subject, text_body, html_body, output_path)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    _iso(brief.timestamp),
                    brief.type,
                    brief.subject,
                    brief.text_body,
                    brief.html_body,
                    brief.output_path,
                ),
            )


class AlertRepository:
    def save(self, alert: Alert) -> None:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO alerts (timestamp, event_title, impact_score, text_body, sent)
                VALUES (?, ?, ?, ?, ?)
                """,
                (_iso(alert.timestamp), alert.event_title, alert.impact_score, alert.text_body, int(alert.sent)),
            )

    def exists_recent(self, event_title: str, now: datetime, dedup_hours: int) -> bool:
        since = now - timedelta(hours=dedup_hours)
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT 1 FROM alerts
                WHERE event_title = ? AND timestamp >= ?
                LIMIT 1
                """,
                (event_title, _iso(since)),
            ).fetchone()
        return row is not None


class SentEmailRepository:
    def save(self, email: SentEmail) -> None:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO sent_emails (timestamp, subject, recipients, status, error_message)
                VALUES (?, ?, ?, ?, ?)
                """,
                (_iso(email.timestamp), email.subject, email.recipients, email.status, email.error_message),
            )


@dataclass(frozen=True)
class SourceState:
    source: str
    kind: str
    state: str
    last_status: str
    since: datetime
    last_ok_at: datetime | None
    detail: str


class SourceHealthRepository:
    """Registros de salud por corrida y estado reportado vigente por fuente."""

    def states(self) -> dict[str, SourceState]:
        with get_connection() as connection:
            rows = connection.execute("SELECT * FROM source_state ORDER BY kind, source").fetchall()
        return {
            row["source"]: SourceState(
                source=row["source"],
                kind=row["kind"],
                state=row["state"],
                last_status=row["last_status"],
                since=datetime.fromisoformat(row["since"]),
                last_ok_at=datetime.fromisoformat(row["last_ok_at"]) if row["last_ok_at"] else None,
                detail=row["detail"] or "",
            )
            for row in rows
        }

    def save_run(self, run_at: datetime, checks: list, states: list[SourceState]) -> None:
        with get_connection() as connection:
            connection.executemany(
                """
                INSERT INTO source_health (run_at, source, kind, status, items, newest_at, detail)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        _iso(run_at),
                        check.source,
                        str(check.kind),
                        str(check.status),
                        check.items,
                        _iso(check.newest_at) if check.newest_at else None,
                        check.detail,
                    )
                    for check in checks
                ],
            )
            connection.executemany(
                """
                INSERT INTO source_state (source, kind, state, last_status, since, last_ok_at, detail)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source) DO UPDATE SET
                    kind = excluded.kind, state = excluded.state, last_status = excluded.last_status,
                    since = excluded.since, last_ok_at = excluded.last_ok_at, detail = excluded.detail
                """,
                [
                    (
                        state.source,
                        state.kind,
                        state.state,
                        state.last_status,
                        _iso(state.since),
                        _iso(state.last_ok_at) if state.last_ok_at else None,
                        state.detail,
                    )
                    for state in states
                ],
            )

    def prune(self, before: datetime) -> int:
        with get_connection() as connection:
            cursor = connection.execute("DELETE FROM source_health WHERE run_at < ?", (_iso(before),))
        return cursor.rowcount
