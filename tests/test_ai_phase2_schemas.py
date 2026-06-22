from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from services.ai.schemas import (
    AiIntermediateRegionalReport,
    AiMacroRegionGroup,
    AiMacroRouterResponse,
    AiPhase2Report,
    AiPhase2RunMetadata,
    AiRoutedNewsInput,
    AiTopicCluster,
    AiTopicRouterResponse,
)


class TestPhase2Schemas:
    def test_routed_news_input_defaults(self) -> None:
        item = AiRoutedNewsInput(
            id="https://example.com",
            timestamp=datetime.now(UTC),
            source="Fed",
            title="x",
            url="https://example.com",
        )
        assert item.country is None
        assert item.region == "Global"
        assert item.impact_score == 0

    def test_macro_region_group_defaults(self) -> None:
        group = AiMacroRegionGroup(region="Chile", relevance="high")
        assert group.country is None
        assert group.main_topics == []
        assert group.news_urls == []
        assert group.cautions == []

    def test_macro_router_response_accepts_valid(self) -> None:
        data = {
            "status": "ok",
            "groups": [
                {
                    "region": "Chile",
                    "country": "Chile",
                    "relevance": "high",
                    "main_topics": ["politica fiscal"],
                    "news_urls": ["https://example.com/1"],
                    "key_facts": ["Hecho 1"],
                    "why_it_matters": "Importante",
                    "cautions": [],
                }
            ],
            "discarded_urls": [],
            "cautions": [],
        }
        resp = AiMacroRouterResponse.model_validate(data)
        assert resp.status == "ok"
        assert len(resp.groups) == 1
        assert resp.groups[0].relevance == "high"

    def test_macro_router_response_rejects_invalid_relevance(self) -> None:
        with pytest.raises(ValidationError):
            AiMacroRegionGroup(region="x", relevance="critical")

    def test_topic_cluster_defaults(self) -> None:
        cluster = AiTopicCluster(region="Chile", topic="tasas", relevance="medium")
        assert cluster.observed_facts == []
        assert cluster.affected_assets == []
        assert cluster.country is None

    def test_topic_router_response_accepts_valid(self) -> None:
        data = {
            "status": "ok",
            "clusters": [
                {
                    "region": "Chile",
                    "topic": "tasas",
                    "relevance": "high",
                    "news_urls": ["https://example.com/1"],
                    "observed_facts": ["Hecho"],
                    "interpretation": ["Lectura"],
                }
            ],
        }
        resp = AiTopicRouterResponse.model_validate(data)
        assert len(resp.clusters) == 1
        assert resp.clusters[0].interpretation == ["Lectura"]

    def test_phase2_report_defaults(self) -> None:
        report = AiPhase2Report(
            status="ok",
            generated_at=datetime.now(UTC),
        )
        assert report.report_type == "phase2_intermediate"
        assert report.regional_reports == []
        assert report.global_summary == []

    def test_phase2_report_with_regional(self) -> None:
        regional = AiIntermediateRegionalReport(
            region="Chile",
            executive_summary=["Punto 1"],
        )
        report = AiPhase2Report(
            status="ok",
            generated_at=datetime.now(UTC),
            regional_reports=[regional],
        )
        assert len(report.regional_reports) == 1
        assert report.regional_reports[0].executive_summary == ["Punto 1"]

    def test_phase2_run_metadata_defaults(self) -> None:
        meta = AiPhase2RunMetadata(
            model="gpt-oss:120b",
            stage="macro_router",
            prompt_name="macro_region_router",
        )
        assert meta.provider == "ollama_cloud"
        assert meta.validation_status == "ok"
        assert meta.output_group_count == 0

    def test_phase2_run_metadata_rejects_invalid_stage(self) -> None:
        with pytest.raises(ValidationError):
            AiPhase2RunMetadata(
                model="x",
                stage="invalid_stage",
                prompt_name="x",
            )
