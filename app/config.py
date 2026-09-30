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
    # Nombre visible del remitente ("DMAC Brief <correo>"). Si EMAIL_FROM ya
    # trae nombre ("Nombre <correo>"), se respeta.
    email_from_name: str = "DMAC Brief · Nix"
    email_to: str = ""
    email_cc: str = ""
    email_logo_path: str = "assets/Dmac_logo.png"
    # Logo embebido en el correo (parte `multipart/related`, referenciado como
    # cid:dmac-logo): se ve aunque Outlook bloquee imagenes externas de un
    # remitente externo, y su fondo blanco va dentro del PNG. Tambien acepta
    # una URL HTTPS; vacio incrusta EMAIL_LOGO_PATH como data URI (previews).
    email_logo_url: str = "cid:dmac-logo"
    email_logo_embed_path: str = "assets/Dmac_logo_email.png"
    # Avisos de salud de fuentes para mantenedores (nunca a la lista del club).
    # Vacio: los cambios de estado solo quedan en el log.
    ops_email_to: str = ""

    # Mailing con suscripcion (MySQL + servicio web de altas y bajas). Apagado,
    # el brief va a EMAIL_TO/EMAIL_CC como siempre. Encendido, va a cada
    # suscriptor `active`, un correo por persona con su link de baja.
    mailing_enabled: bool = False
    # URL publica HTTPS del servicio de suscripcion (Tailscale Funnel), sin "/"
    # final. Arma los links de confirmacion y baja.
    mailing_public_url: str = ""
    mailing_web_host: str = "0.0.0.0"
    mailing_web_port: int = 8080
    # Link de confirmacion valido por estos dias; despues hay que volver a
    # inscribirse.
    mailing_confirm_ttl_days: int = 7
    # Frenos a abusos del formulario: minutos entre correos de confirmacion a
    # una misma direccion y maximo de correos de confirmacion por hora.
    mailing_confirm_resend_minutes: int = 10
    mailing_confirm_max_per_hour: int = 60
    mysql_host: str = "mysql"
    mysql_port: int = 3306
    mysql_database: str = "dmac_mailing"
    mysql_user: str = "dmac_mailing"
    mysql_password: str = ""

    bcentral_user: str = ""
    bcentral_password: str = ""
    bcentral_credentials_file: str = ""
    bcentral_tpm_series: str = "F022.TPM.TIN.D001.NO.Z.D"
    bcentral_ipc_series: str = "F074.IPC.VAR.Z.Z.C.M"
    bcentral_unemployment_series: str = "F049.DES.TAS.INE9.10.M"
    bcentral_usdpen_series: str = "F072.PEN.USD.N.O.D"
    # Series verificadas con SearchSeries el 2026-09-29.
    bcentral_ipc12_series: str = "F074.IPC.V12.Z.EP23.C.M"
    bcentral_imacec_series: str = "F032.IMC.V12.Z.Z.2018.Z.Z.0.M"
    bcentral_dolar_observado_series: str = "F073.TCO.PRE.Z.D"
    bcentral_uf_series: str = "F073.UFF.PRE.Z.D"
    bcentral_copper_series: str = "F019.PPB.PRE.100.D"
    bcentral_timeout_seconds: float = 20.0

    market_data_provider: str = "yfinance"
    database_url: str = "sqlite:///storage/dmac_market_brief.db"

    high_impact_threshold: int = 8
    alert_monitor_enabled: bool = False
    alert_dedup_hours: int = 3
    news_mention_lookback_hours: int = 720
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
    ollama_model: str = "gpt-oss:120b"
    ollama_timeout_seconds: float = 45.0
    ollama_temperature: float = 0.2
    ollama_max_retries: int = 2

    @field_validator("email_to", "email_cc", "ops_email_to", "rss_feeds", mode="before")
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
    def ops_email_to_list(self) -> list[str]:
        return self._split_csv(self.ops_email_to)

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
