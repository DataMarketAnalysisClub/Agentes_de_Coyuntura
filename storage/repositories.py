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


class BriefRepository:
    def save(self, brief: Brief) -> None:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO briefs (timestamp, type, subject, text_body, html_body, whatsapp_body, output_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _iso(brief.timestamp),
                    brief.type,
                    brief.subject,
                    brief.text_body,
                    brief.html_body,
                    brief.whatsapp_body,
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
