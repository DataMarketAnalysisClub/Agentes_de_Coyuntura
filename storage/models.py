from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class MarketSnapshot:
    timestamp: datetime
    symbol: str
    name: str
    price: float | None
    change_pct: float | None
    source: str
    # Cierres diarios recientes (antiguo -> reciente) para graficos del correo.
    # Solo en memoria: no se persiste en SQLite.
    history: tuple[float, ...] = field(default=(), compare=False, repr=False)


@dataclass(frozen=True)
class NewsItem:
    timestamp: datetime
    source: str
    title: str
    url: str
    summary: str
    region: str
    topic: str
    impact_score: int = 0


@dataclass(frozen=True)
class Brief:
    timestamp: datetime
    type: str
    subject: str
    text_body: str
    html_body: str
    output_path: str


@dataclass(frozen=True)
class Alert:
    timestamp: datetime
    event_title: str
    impact_score: int
    text_body: str
    sent: bool = False


@dataclass(frozen=True)
class SentEmail:
    timestamp: datetime
    subject: str
    recipients: str
    status: str
    error_message: str = ""
