from datetime import UTC, datetime
from unittest.mock import patch

from app.config import Settings
from services.ai.editorial_writer import (
    EditorialWriterResult,
    build_deterministic_editorial,
    run_editorial_writer,
)
from services.ai.schemas import AiIntermediateRegionalReport, AiPhase2Report
from storage.models import MarketSnapshot


def _make_settings(
    ai_enabled: bool = True,
    ai_dry_run: bool = True,
    ollama_api_key: str = "test-key",
    ollama_model: str = "gpt-oss:120b",
) -> Settings:
    return Settings(
        ai_enabled=ai_enabled,
        ai_dry_run=ai_dry_run,
        ollama_api_key=ollama_api_key,
        ollama_model=ollama_model,
        ollama_base_url="https://ollama.com",
        ollama_timeout_seconds=5.0,
        ollama_temperature=0.2,
        ollama_max_retries=1,
    )


def _make_report() -> AiPhase2Report:
    regional = AiIntermediateRegionalReport(
        region="Chile",
        country="Chile",
        executive_summary=["Hacienda anuncia politica fiscal."],
    )
    return AiPhase2Report(
        status="ok",
        generated_at=datetime.now(UTC),
        regional_reports=[regional],
        global_summary=["Mercados estables."],
        editorial_cautions=["Cautela general."],
    )


def _make_snapshots() -> list[MarketSnapshot]:
    return [
        MarketSnapshot(
            timestamp=datetime.now(UTC),
            symbol="USDCLP",
            name="USD/CLP",
            price=900.0,
            change_pct=1.5,
            source="yfinance",
        ),
        MarketSnapshot(
            timestamp=datetime.now(UTC),
            symbol="IPSA",
            name="IPSA",
            price=5000.0,
            change_pct=-0.3,
            source="yfinance",
        ),
    ]


class TestEditorialWriter:
    def test_skipped_when_ai_disabled_returns_fallback(self) -> None:
        settings = _make_settings(ai_enabled=False)
        with patch("services.ai.editorial_writer.OllamaCloudClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = False
            mock_client.is_dry_run.return_value = True
            result = run_editorial_writer(_make_report(), _make_snapshots())
        assert isinstance(result, EditorialWriterResult)
        assert result.response is None
        assert result.metadata.validation_status == "skipped"
        assert result.fallback is not None
        assert result.email is not None
        assert any("deterministic" in c.lower() for c in result.email.editorial_cautions)

    def test_dry_run_returns_valid(self) -> None:
        settings = _make_settings(ai_enabled=True, ai_dry_run=True)
        valid_json = (
            '{"status":"ok","generated_at":"2026-06-20T12:00:00Z",'
            '"subject":"DMAC Coyuntura","preheader":"Resumen",'
            '"headline":"Coyuntura","executive_summary":["Punto 1"],'
            '"sections":[{"heading":"Chile","body":["Parrafo"],"bullets":["Hecho"]}],'
            '"chart_specs":[],"source_notes":["Fed"],"editorial_cautions":["Cautela"]}'
        )
        with patch("services.ai.editorial_writer.OllamaCloudClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = True
            mock_client.is_dry_run.return_value = True
            mock_client.settings.ai_strict_json = True
            mock_client.chat_json.return_value = valid_json
            result = run_editorial_writer(_make_report(), _make_snapshots())
        assert result.ok is True
        assert result.response is not None
        assert result.response.subject == "DMAC Coyuntura"
        assert len(result.response.sections) == 1

    def test_invalid_json_returns_fallback(self) -> None:
        settings = _make_settings(ai_enabled=True, ai_dry_run=False)
        with patch("services.ai.editorial_writer.OllamaCloudClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = True
            mock_client.is_dry_run.return_value = False
            mock_client.settings.ai_strict_json = True
            mock_client.chat_json.return_value = "not json"
            result = run_editorial_writer(_make_report(), _make_snapshots())
        assert result.response is None
        assert result.metadata.validation_status == "invalid_json"
        assert result.fallback is not None
        assert result.email is not None

    def test_ollama_error_returns_fallback(self) -> None:
        settings = _make_settings(ai_enabled=True, ai_dry_run=False)
        from services.ai.ollama_client import OllamaCloudError

        with patch("services.ai.editorial_writer.OllamaCloudClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = True
            mock_client.is_dry_run.return_value = False
            mock_client.chat_json.side_effect = OllamaCloudError("boom")
            result = run_editorial_writer(_make_report(), _make_snapshots())
        assert result.response is None
        assert result.metadata.validation_status == "skipped"
        assert result.fallback is not None

    def test_filter_chart_specs_drops_unknown_ids(self) -> None:
        settings = _make_settings(ai_enabled=True, ai_dry_run=True)
        valid_json = (
            '{"status":"ok","generated_at":"2026-06-20T12:00:00Z",'
            '"subject":"DMAC","headline":"Coyuntura",'
            '"sections":[{"heading":"Chile","chart_ids":["assets_table","unknown_id"]}],'
            '"chart_specs":['
            '{"chart_id":"assets_table","chart_type":"table_assets","title":"X"},'
            '{"chart_id":"unknown_id","chart_type":"bar_change_pct","title":"Y"}'
            ']}'
        )
        with patch("services.ai.editorial_writer.OllamaCloudClient") as mock_client_class:
            mock_client = mock_client_class.return_value
            mock_client.settings = settings
            mock_client.is_enabled.return_value = True
            mock_client.is_dry_run.return_value = True
            mock_client.settings.ai_strict_json = True
            mock_client.chat_json.return_value = valid_json
            result = run_editorial_writer(
                _make_report(),
                _make_snapshots(),
                news=[],
            )
        assert result.response is not None
        assert len(result.response.chart_specs) == 1
        assert result.response.chart_specs[0].chart_id == "assets_table"
        assert result.response.sections[0].chart_ids == ["assets_table"]

    def test_deterministic_editorial_basic(self) -> None:
        report = _make_report()
        email = build_deterministic_editorial(report, _make_snapshots(), ["assets_table"])
        assert email.status == "ok"
        assert email.subject != ""
        assert email.sections[0].heading == "Chile"
        assert any("deterministic" in c.lower() for c in email.editorial_cautions)
        assert len(email.chart_specs) == 1
        assert email.chart_specs[0].chart_id == "assets_table"
        assert any(s.heading == "Visualizaciones" for s in email.sections)

    def test_deterministic_editorial_market_context(self) -> None:
        report = _make_report()
        email = build_deterministic_editorial(report, _make_snapshots(), [])
        assert len(email.market_context) == 2
        assert "USD/CLP" in email.market_context[0]
