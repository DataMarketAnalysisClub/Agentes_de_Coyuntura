from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    tz: str = "America/Santiago"
    dry_run: bool = True

    email_enabled: bool = False
    alert_email_enabled: bool = False
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    email_from: str = ""
    email_to: list[str] = Field(default_factory=list)
    email_cc: list[str] = Field(default_factory=list)

    bcentral_user: str = ""
    bcentral_password: str = ""
    fred_api_key: str = ""
    alpha_vantage_api_key: str = ""

    market_data_provider: str = "yfinance"
    database_url: str = "sqlite:///storage/dmac_market_brief.db"

    high_impact_threshold: int = 8
    alert_dedup_hours: int = 3
    rss_feeds: list[str] = Field(default_factory=list)

    @field_validator("email_to", "email_cc", "rss_feeds", mode="before")
    @classmethod
    def split_csv(cls, value: object) -> list[str]:
        if value is None or value == "":
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return []

    @property
    def sqlite_path(self) -> Path:
        if not self.database_url.startswith("sqlite:///"):
            msg = "Only sqlite:/// DATABASE_URL is supported in the MVP"
            raise ValueError(msg)
        return Path(self.database_url.removeprefix("sqlite:///"))

    def ensure_runtime_dirs(self) -> None:
        for path in [
            Path("outputs/briefs"),
            Path("outputs/alerts"),
            Path("outputs/whatsapp"),
            Path("logs"),
            Path("storage"),
        ]:
            path.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_runtime_dirs()
    return settings
