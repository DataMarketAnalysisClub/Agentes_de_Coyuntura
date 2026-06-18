import logging

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


class BCentralClient:
    """Placeholder for Banco Central de Chile data series."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    def fetch_policy_rate(self) -> float | None:
        if not self.settings.bcentral_user or not self.settings.bcentral_password:
            logger.warning("BCentral credentials missing; TPM placeholder unavailable")
            return None
        logger.warning("BCentral API integration not implemented in MVP")
        return None

    def fetch_inflation(self) -> float | None:
        if not self.settings.bcentral_user or not self.settings.bcentral_password:
            logger.warning("BCentral credentials missing; inflation placeholder unavailable")
            return None
        logger.warning("BCentral API integration not implemented in MVP")
        return None
