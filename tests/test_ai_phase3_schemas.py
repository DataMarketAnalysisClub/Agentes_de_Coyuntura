from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from services.ai.schemas import (
    AiChartSpec,
    AiEditorialEmail,
    AiEditorialRunMetadata,
    AiEditorialSection,
    AiPhase3RunResult,
)


class TestPhase3Schemas:
    def test_chart_spec_defaults(self) -> None:
        spec = AiChartSpec(
            chart_id="change_pct_bar",
            chart_type="bar_change_pct",
            title="Variacion %",
        )
        assert spec.subtitle == ""
        assert spec.source_label == "Datos: fuentes internas DMAC"

    def test_chart_spec_rejects_invalid_type(self) -> None:
        with pytest.raises(ValidationError):
            AiChartSpec(
                chart_id="x",
                chart_type="pie_chart",
                title="x",
            )

    def test_editorial_section_defaults(self) -> None:
        section = AiEditorialSection(heading="Chile")
        assert section.body == []
        assert section.bullets == []
        assert section.chart_ids == []
        assert section.cautions == []

    def test_editorial_email_minimum_fields(self) -> None:
        email = AiEditorialEmail(
            status="ok",
            generated_at=datetime.now(UTC),
            subject="DMAC Coyuntura",
        )
        assert email.report_type == "phase3_editorial_email"
        assert email.sections == []
        assert email.chart_specs == []
        assert email.executive_summary == []

    def test_editorial_email_with_full_fields(self) -> None:
        section = AiEditorialSection(
            heading="Chile",
            body=["Parrafo 1"],
            bullets=["Hecho 1"],
            chart_ids=["change_pct_bar"],
            cautions=["Cautela 1"],
        )
        chart = AiChartSpec(
            chart_id="change_pct_bar",
            chart_type="bar_change_pct",
            title="Variacion %",
        )
        email = AiEditorialEmail(
            status="ok",
            generated_at=datetime.now(UTC),
            subject="DMAC Coyuntura",
            preheader="Resumen breve",
            headline="Coyuntura",
            executive_summary=["Punto 1"],
            market_context=["Contexto 1"],
            sections=[section],
            risk_flags=["Flag 1"],
            chart_specs=[chart],
            source_notes=["Fed"],
            editorial_cautions=["Cautela general"],
        )
        assert len(email.sections) == 1
        assert email.sections[0].chart_ids == ["change_pct_bar"]
        assert len(email.chart_specs) == 1

    def test_editorial_run_metadata_defaults(self) -> None:
        meta = AiEditorialRunMetadata(model="gpt-oss:120b")
        assert meta.stage == "editorial_writer"
        assert meta.prompt_name == "editorial_email_writer"
        assert meta.validation_status == "ok"
        assert meta.output_sections_count == 0

    def test_phase3_run_result_defaults(self) -> None:
        email = AiEditorialEmail(
            status="ok",
            generated_at=datetime.now(UTC),
            subject="x",
        )
        meta = AiEditorialRunMetadata(model="m")
        result = AiPhase3RunResult(
            editorial=email,
            metadata=meta,
        )
        assert result.chart_specs == []
        assert result.rendered_chart_ids == []
        assert result.fallback_used is False

    def test_editorial_email_rejects_invalid_status(self) -> None:
        with pytest.raises(ValidationError):
            AiEditorialEmail(
                status="error",
                generated_at=datetime.now(UTC),
                subject="x",
            )
