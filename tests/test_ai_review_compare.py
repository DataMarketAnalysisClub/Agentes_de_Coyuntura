"""Tests for the AI review comparison job (fallback vs IA)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from app.config import Settings
from jobs.ai_review_compare import run_ai_review_compare
from storage.models import MarketSnapshot, NewsItem


def _make_settings(*, ai_dry_run: bool = True, ai_key: str = "") -> Settings:
    return Settings(
        ai_enabled=False,
        ai_dry_run=ai_dry_run,
        ollama_api_key=ai_key,
        ollama_model="gpt-oss:120b",
        ollama_base_url="https://ollama.com",
        ollama_timeout_seconds=5.0,
        ollama_temperature=0.2,
        ollama_max_retries=1,
        ai_output_dir="outputs/ai_test",
    )


def _make_news() -> list[NewsItem]:
    now = datetime.now(UTC)
    return [
        NewsItem(timestamp=now, source="Federal Reserve",
                 title="Fed cut rates by 25bps amid cooling inflation",
                 url="https://example.com/1", summary="Fed cut rates",
                 region="EE.UU.", topic="bancos centrales", impact_score=9),
        NewsItem(timestamp=now, source="Ministerio de Hacienda",
                 title="Hacienda fija trayectoria fiscal para 2026",
                 url="https://example.com/2", summary="Politica fiscal",
                 region="Chile", topic="politica fiscal", impact_score=8),
    ]


def _make_snaps() -> list[MarketSnapshot]:
    now = datetime.now(UTC)
    return [
        MarketSnapshot(timestamp=now, symbol="USDCLP", name="USD/CLP",
                       price=900.0, change_pct=1.5, source="yfinance"),
        MarketSnapshot(timestamp=now, symbol="COPPER", name="Cobre",
                       price=4.5, change_pct=3.0, source="yfinance"),
    ]


def test_compare_without_ollama_key_creates_fallback_only(tmp_path: Path) -> None:
    """When OLLAMA_API_KEY is empty, only the fallback bundle is produced."""
    settings = _make_settings(ai_key="")
    with patch("jobs.ai_review_compare.get_settings", return_value=settings):
        out = run_ai_review_compare(
            news=_make_news(),
            snapshots=_make_snaps(),
        )
    assert out is not None
    assert (out / "fallback" / "review_checklist.md").exists()
    assert (out / "comparison_report.md").exists()
    assert (out / "comparison_summary.json").exists()
    assert not (out / "models").exists()

    summary = json.loads((out / "comparison_summary.json").read_text(encoding="utf-8"))
    assert summary["fallback_ready"] is True
    assert summary["ai_ready"] is False
    variants = {v["name"]: v for v in summary["variants"]}
    assert "fallback" in variants
    assert "models" in variants
    assert variants["models"]["ai_run_status"] in {
        "missing_ollama_api_key",
    }


def test_compare_skips_ia_when_dry_run_active(tmp_path: Path) -> None:
    """When AI_DRY_RUN=true, IA variants are skipped even if a key is set."""
    settings = _make_settings(ai_dry_run=True, ai_key="dummy-key")
    with patch("jobs.ai_review_compare.get_settings", return_value=settings):
        out = run_ai_review_compare(
            news=_make_news(),
            snapshots=_make_snaps(),
        )
    assert out is not None
    summary = json.loads((out / "comparison_summary.json").read_text(encoding="utf-8"))
    assert summary["ai_ready"] is False
    variants = {v["name"]: v for v in summary["variants"]}
    assert variants["models"]["ai_run_status"] == "dry_run_active"


def test_compare_runs_ia_for_each_model_when_ready(tmp_path: Path) -> None:
    """When AI is ready, runs one variant per model listed."""
    settings = _make_settings(ai_dry_run=False, ai_key="dummy-key")
    settings.ollama_model = "gpt-oss:120b"

    from services.ai.schemas import (
        AiEditorialEmail,
        AiEditorialRunMetadata,
        AiEditorialSection,
    )

    fake_email = AiEditorialEmail(
        status="ok",
        generated_at=datetime.now(UTC),
        subject="DMAC Coyuntura: IA",
        preheader="IA ejecutada",
        headline="IA lidera la jornada",
        executive_summary=["Punto 1"],
        market_context=["USD/CLP: +1.50%"],
        sections=[AiEditorialSection(heading="Chile", body=["b"], bullets=["x"])],
        risk_flags=[],
        chart_specs=[],
        source_notes=["Federal Reserve", "Hacienda", "ECB"],
        editorial_cautions=["Cautela"],
    )
    fake_meta = AiEditorialRunMetadata(model="gpt-oss:120b", validation_status="ok")

    class _FakeResult:
        editorial = fake_email
        chart_fragments: dict = {}
        metadata = [fake_meta]
        html = "<html></html>"
        markdown = "# md"
        fallback_used = False
        phase2_report = None
        input_news = _make_news()
        input_snapshots = _make_snaps()

        @property
        def ok(self) -> bool:
            return True

    with patch("jobs.ai_review_compare.get_settings", return_value=settings), \
         patch.dict("os.environ", {"OLLAMA_COMPARE_MODELS": "gpt-oss:120b,other-model"}), \
         patch("jobs.ai_review_compare.run_phase3_pipeline", return_value=_FakeResult()):
        out = run_ai_review_compare(
            news=_make_news(),
            snapshots=_make_snaps(),
        )

    assert out is not None
    assert (out / "models" / "gpt-oss_120b" / "review_checklist.md").exists()
    assert (out / "models" / "other-model" / "review_checklist.md").exists()

    summary = json.loads((out / "comparison_summary.json").read_text(encoding="utf-8"))
    assert summary["ai_ready"] is True
    assert summary["fallback_ready"] is True
    variants = {v["name"]: v for v in summary["variants"]}
    assert variants["model:gpt-oss:120b"]["status"] == "ok"
    assert variants["model:other-model"]["status"] == "ok"
