import logging

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class FredClient:
    """Placeholder for future FRED macro series."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def fetch_series_latest(self, series_id: str) -> float | None:
        if not self.settings.fred_api_key:
            logger.warning("FRED API key missing", extra={"series_id": series_id})
            return None
        logger.warning("FRED API integration not implemented in MVP", extra={"series_id": series_id})
        return None
