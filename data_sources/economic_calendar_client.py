import logging
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EconomicEvent:
    timestamp: datetime
    country: str
    title: str
    importance: str


class EconomicCalendarClient:
    """Placeholder for an economic calendar provider."""

    def fetch_upcoming_events(self) -> list[EconomicEvent]:
        logger.warning("Economic calendar integration not implemented in MVP")
        return []
