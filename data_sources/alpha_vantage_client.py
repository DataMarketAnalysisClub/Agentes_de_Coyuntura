import logging

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class AlphaVantageClient:
    """Placeholder for future Alpha Vantage quotes."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def fetch_quote(self, symbol: str) -> dict[str, float] | None:
        if not self.settings.alpha_vantage_api_key:
            logger.warning("Alpha Vantage API key missing", extra={"symbol": symbol})
            return None
        logger.warning("Alpha Vantage integration not implemented in MVP", extra={"symbol": symbol})
        return None
