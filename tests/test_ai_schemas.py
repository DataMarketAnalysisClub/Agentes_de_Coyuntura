import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from services.ai.schemas import (
    AiBriefDraft,
    AiHighImpactDecision,
    AiMarketSnapshotInput,
    AiNewsInput,
    AiRunMetadata,
    AiSmokeTestResponse,
)


class TestAiSchemas:
    def test_ai_news_input_defaults(self) -> None:
        item = AiNewsInput(
            timestamp=datetime.now(UTC),
            source="Federal Reserve",
            title="Fed cut rates",
            url="https://example.com/fed",
        )
        assert item.region == "Global"
        assert item.topic == "macro general"
        assert item.impact_score == 0
        assert item.summary == ""

    def test_ai_smoke_test_response_accepts_valid(self) -> None:
        data = {
            "status": "ok",
            "summary": "Resumen de prueba",
            "high_impact_titles": ["Titulo 1"],
            "cautions": ["Cautela 1"],
        }
        resp = AiSmokeTestResponse.model_validate(data)
        assert resp.status == "ok"
        assert resp.summary == "Resumen de prueba"
        assert resp.high_impact_titles == ["Titulo 1"]

    def test_ai_smoke_test_response_rejects_invalid_status(self) -> None:
        with pytest.raises(ValidationError):
            AiSmokeTestResponse.model_validate({"status": "error", "summary": "x"})

    def test_ai_smoke_test_response_defaults_empty_lists(self) -> None:
        resp = AiSmokeTestResponse.model_validate({"status": "ok", "summary": "x"})
        assert resp.high_impact_titles == []
        assert resp.cautions == []

    def test_ai_high_impact_decision_confidence_range(self) -> None:
        with pytest.raises(ValidationError):
            AiHighImpactDecision(
                title="x",
                url="https://example.com",
                source="s",
                region="Chile",
                topic="tasas",
                impact_level="high",
                reason="r",
                confidence=1.5,
            )

    def test_ai_high_impact_decision_accepts_zero_confidence(self) -> None:
        item = AiHighImpactDecision(
            title="x",
            url="https://example.com",
            source="s",
            region="Chile",
            topic="tasas",
            impact_level="low",
            reason="r",
            confidence=0.0,
        )
        assert item.confidence == 0.0

    def test_ai_brief_draft_minimum_fields(self) -> None:
        draft = AiBriefDraft(
            subject="Brief del dia",
            executive_summary=["Punto 1"],
        )
        assert draft.subject == "Brief del dia"
        assert draft.facts == []
        assert draft.risks == []

    def test_ai_market_snapshot_input_nullable_price(self) -> None:
        snap = AiMarketSnapshotInput(symbol="USDCLP", name="USD/CLP")
        assert snap.price is None
        assert snap.change_pct is None

    def test_ai_run_metadata_defaults(self) -> None:
        meta = AiRunMetadata(model="gpt-oss:120b", prompt_name="json_smoke_test")
        assert meta.provider == "ollama_cloud"
        assert meta.validation_status == "ok"
        assert meta.dry_run is False

    def test_ai_news_input_serializes_datetime_to_json(self) -> None:
        item = AiNewsInput(
            timestamp=datetime(2026, 6, 20, 12, 0, tzinfo=UTC),
            source="ECB",
            title="x",
            url="https://example.com",
        )
        dumped = item.model_dump(mode="json")
        assert isinstance(json.dumps(dumped), str)
        assert "2026" in dumped["timestamp"]
