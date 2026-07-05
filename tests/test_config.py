from pathlib import Path

from app.config import Settings


def test_load_bcentral_credentials_file_two_line_format(tmp_path: Path) -> None:
    credentials = tmp_path / "credentials.txt"
    credentials.write_text("user@example.com\nsecret-password\n", encoding="utf-8")
    settings = Settings(bcentral_credentials_file=str(credentials))

    settings.load_bcentral_credentials_file()

    assert settings.bcentral_user == "user@example.com"
    assert settings.bcentral_password == "secret-password"


def test_bcentral_env_credentials_take_precedence(tmp_path: Path) -> None:
    credentials = tmp_path / "credentials.txt"
    credentials.write_text("file-user@example.com\nfile-secret\n", encoding="utf-8")
    settings = Settings(
        bcentral_user="env-user@example.com",
        bcentral_password="env-secret",
        bcentral_credentials_file=str(credentials),
    )

    settings.load_bcentral_credentials_file()

    assert settings.bcentral_user == "env-user@example.com"
    assert settings.bcentral_password == "env-secret"


def test_alert_monitor_disabled_by_default() -> None:
    settings = Settings()

    assert settings.alert_monitor_enabled is False


def test_news_mention_lookback_default() -> None:
    settings = Settings()

    assert settings.news_mention_lookback_hours == 720
