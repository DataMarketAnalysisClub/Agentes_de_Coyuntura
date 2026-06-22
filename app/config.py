from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
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
    email_to: str = ""
    email_cc: str = ""
    email_logo_path: str = "assets/Dmac_logo.png"

    bcentral_user: str = ""
    bcentral_password: str = ""
    bcentral_credentials_file: str = ""
    bcentral_tpm_series: str = "F022.TPM.TIN.D001.NO.Z.D"
    bcentral_ipc_series: str = "F074.IPC.VAR.Z.Z.C.M"
    bcentral_timeout_seconds: float = 20.0
    fred_api_key: str = ""
    alpha_vantage_api_key: str = ""

    market_data_provider: str = "yfinance"
    database_url: str = "sqlite:///storage/dmac_market_brief.db"

    high_impact_threshold: int = 8
    alert_dedup_hours: int = 3
    rss_feeds: str = ""

    ai_enabled: bool = False
    ai_dry_run: bool = True
    ai_strict_json: bool = True
    ai_max_news_items: int = 30
    ai_output_dir: str = "outputs/ai"
    ai_max_groups: int = 6
    ai_max_news_per_group: int = 10
    ai_charts_enabled: bool = True
    ai_max_charts: int = 4
    ai_chart_output_dir: str = "outputs/ai/charts"
    ai_brief_enabled: bool = False

    ollama_base_url: str = "https://ollama.com"
    ollama_api_key: str = ""
    ollama_model: str = ""
    ollama_timeout_seconds: float = 45.0
    ollama_temperature: float = 0.2
    ollama_max_retries: int = 2

    @field_validator("email_to", "email_cc", "rss_feeds", mode="before")
    @classmethod
    def _coerce_list_field(cls, value: object) -> object:
        if value is None or value == "":
            return ""
        return str(value)

    @staticmethod
    def _split_csv(value: str) -> list[str]:
        if not value:
            return []
        return [item.strip() for item in value.split(",") if item.strip()]

    @property
    def email_to_list(self) -> list[str]:
        return self._split_csv(self.email_to)

    @property
    def email_cc_list(self) -> list[str]:
        return self._split_csv(self.email_cc)

    @property
    def rss_feeds_list(self) -> list[str]:
        return self._split_csv(self.rss_feeds)

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
            Path("outputs/ai"),
            Path("logs"),
            Path("storage"),
        ]:
            path.mkdir(parents=True, exist_ok=True)

    def load_bcentral_credentials_file(self) -> None:
        """Load BCCh credentials from a two-line external file when configured."""

        if self.bcentral_user and self.bcentral_password:
            return
        if not self.bcentral_credentials_file:
            return

        credentials_path = Path(self.bcentral_credentials_file).expanduser()
        if not credentials_path.exists():
            return

        lines = [line.strip() for line in credentials_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if len(lines) >= 2:
            if not self.bcentral_user:
                self.bcentral_user = lines[0]
            if not self.bcentral_password:
                self.bcentral_password = lines[1]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.load_bcentral_credentials_file()
    settings.ensure_runtime_dirs()
    return settings
