import sqlite3
from pathlib import Path

from app.config import Settings, get_settings


def get_connection(settings: Settings | None = None) -> sqlite3.Connection:
    """Return a SQLite connection and ensure parent directory exists."""

    current_settings = settings or get_settings()
    db_path = current_settings.sqlite_path
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def init_db(settings: Settings | None = None) -> None:
    """Create MVP tables if they do not exist."""

    with get_connection(settings) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS market_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                name TEXT NOT NULL,
                price REAL,
                change_pct REAL,
                source TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS news_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                summary TEXT,
                region TEXT,
                topic TEXT,
                impact_score INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS news_mentions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                mentioned_at TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                url TEXT NOT NULL,
                summary TEXT,
                region TEXT,
                topic TEXT,
                impact_score INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS briefs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                type TEXT NOT NULL,
                subject TEXT NOT NULL,
                text_body TEXT NOT NULL,
                html_body TEXT NOT NULL,
                output_path TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                event_title TEXT NOT NULL,
                impact_score INTEGER NOT NULL,
                text_body TEXT NOT NULL,
                sent INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS sent_emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                subject TEXT NOT NULL,
                recipients TEXT NOT NULL,
                status TEXT NOT NULL,
                error_message TEXT
            );
            """
        )
        _migrate_briefs_table(connection)


def _migrate_briefs_table(connection: sqlite3.Connection) -> None:
    legacy_column = "whats" + "app_body"
    columns = [row["name"] for row in connection.execute("PRAGMA table_info(briefs)").fetchall()]
    if legacy_column not in columns:
        return

    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS briefs_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            type TEXT NOT NULL,
            subject TEXT NOT NULL,
            text_body TEXT NOT NULL,
            html_body TEXT NOT NULL,
            output_path TEXT NOT NULL
        );

        INSERT INTO briefs_new (id, timestamp, type, subject, text_body, html_body, output_path)
        SELECT id, timestamp, type, subject, text_body, html_body, output_path
        FROM briefs;

        DROP TABLE briefs;
        ALTER TABLE briefs_new RENAME TO briefs;
        """
    )


def database_path(settings: Settings | None = None) -> Path:
    return (settings or get_settings()).sqlite_path
