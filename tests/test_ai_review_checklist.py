import json
from datetime import UTC, datetime
from pathlib import Path

from services.ai.review_checklist import (
    _detect_known_issues,
    build_review_checklist,
    build_review_summary,
    save_review_bundle,
)
from services.ai.schemas import (
    AiEditorialEmail,
    AiEditorialRunMetadata,
    AiEditorialSection,
    AiPhase2RunMetadata,
)


def _make_email(
    subject: str = "DMAC Coyuntura - 20 jun 2026",
    sections: list[AiEditorialSection] | None = None,
    chart_specs: list | None = None,
) -> AiEditorialEmail:
    return AiEditorialEmail(
        status="ok",
        generated_at=datetime.now(UTC),
        subject=subject,
        preheader="Resumen breve",
        headline="Coyuntura regional",
        executive_summary=["Punto 1", "Punto 2"],
        market_context=["USD/CLP: +1.50%"],
        sections=sections or [AiEditorialSection(heading="Chile", body=["Parrafo"])],
        risk_flags=["Flag 1"],
        chart_specs=chart_specs or [],
        source_notes=["Federal Reserve"],
        editorial_cautions=["Cautela general"],
    )


def _make_metadata() -> list:
    return [
        AiPhase2RunMetadata(
            model="gpt-oss:120b",
            stage="macro_router",
            prompt_name="macro_region_router",
            validation_status="skipped",
        ),
        AiEditorialRunMetadata(
            model="gpt-oss:120b",
            validation_status="skipped",
        ),
    ]


class TestReviewChecklist:
    def test_build_review_summary_basic(self) -> None:
        email = _make_email()
        summary = build_review_summary(
            email=email,
            metadata=_make_metadata(),
            fallback_used=True,
            news_count=20,
            snapshot_count=5,
            chart_count=3,
            ai_enabled=False,
            ai_dry_run=True,
        )
        assert summary["review_status"] == "pending"
        assert summary["fallback_used"] is True
        assert summary["news_count"] == 20
        assert summary["chart_count"] == 3
        assert summary["section_count"] == 1
        assert len(summary["validation_statuses"]) == 2

    def test_build_review_summary_with_known_issues(self) -> None:
        from services.ai.schemas import AiChartSpec

        specs = [
            AiChartSpec(
                chart_id=f"chart_{i}",
                chart_type="bar_change_pct",
                title=f"Chart {i}",
            )
            for i in range(6)
        ]
        email = _make_email(chart_specs=specs)
        issues = _detect_known_issues(email, fallback_used=True, news_count=20)
        assert any("fallback" in i.lower() for i in issues)
        assert any("demasiados graficos" in i.lower() for i in issues)

    def test_detect_known_issues_empty_email(self) -> None:
        email = AiEditorialEmail(
            status="ok",
            generated_at=datetime.now(UTC),
            subject="",
            executive_summary=[],
            sections=[],
            editorial_cautions=[],
        )
        issues = _detect_known_issues(email, fallback_used=False, news_count=0)
        assert any("resumen ejecutivo vacio" in i.lower() for i in issues)
        assert any("no hay secciones" in i.lower() for i in issues)
        assert any("asunto vacio" in i.lower() for i in issues)
        assert any("no hay cautelas" in i.lower() for i in issues)
        assert any("no hay noticias" in i.lower() for i in issues)

    def test_detect_known_issues_orphan_charts(self) -> None:
        from services.ai.schemas import AiChartSpec

        spec = AiChartSpec(
            chart_id="change_pct_bar",
            chart_type="bar_change_pct",
            title="Variacion %",
        )
        section = AiEditorialSection(
            heading="Chile",
            body=["Parrafo"],
            chart_ids=["impact_ranking_bar"],
        )
        email = _make_email(sections=[section], chart_specs=[spec])
        issues = _detect_known_issues(email, fallback_used=False, news_count=10)
        assert any("change_pct_bar" in i for i in issues)

    def test_build_review_checklist_contains_sections(self) -> None:
        email = _make_email()
        summary = build_review_summary(
            email=email,
            metadata=_make_metadata(),
            fallback_used=False,
            news_count=15,
            snapshot_count=3,
            chart_count=2,
            ai_enabled=True,
            ai_dry_run=True,
        )
        checklist = build_review_checklist(email, summary)
        assert "# Checklist Revision Editorial" in checklist
        assert "## Claridad" in checklist
        assert "## Trazabilidad" in checklist
        assert "## Prudencia financiera" in checklist
        assert "## Estructura" in checklist
        assert "## Graficos" in checklist
        assert "## Decision" in checklist
        assert "## Notas del revisor" in checklist

    def test_build_review_checklist_includes_summary(self) -> None:
        email = _make_email()
        summary = build_review_summary(
            email=email,
            metadata=[],
            fallback_used=True,
            news_count=30,
            snapshot_count=5,
            chart_count=4,
            ai_enabled=False,
            ai_dry_run=True,
        )
        checklist = build_review_checklist(email, summary)
        assert "Fallback usado:** True" in checklist
        assert "Noticias input:** 30" in checklist
        assert "Graficos renderizados:** 4" in checklist

    def test_build_review_checklist_includes_known_issues(self) -> None:
        email = _make_email()
        summary = build_review_summary(
            email=email,
            metadata=[],
            fallback_used=True,
            news_count=0,
            snapshot_count=0,
            chart_count=0,
            ai_enabled=False,
            ai_dry_run=True,
        )
        checklist = build_review_checklist(email, summary)
        assert "## Problemas detectados automaticamente" in checklist
        assert "fallback" in checklist.lower()

    def test_save_review_bundle_creates_files(self, tmp_path: Path) -> None:
        email = _make_email()
        summary = build_review_summary(
            email=email,
            metadata=_make_metadata(),
            fallback_used=False,
            news_count=10,
            snapshot_count=3,
            chart_count=0,
            ai_enabled=True,
            ai_dry_run=True,
        )
        checklist = build_review_checklist(email, summary)

        review_dir = tmp_path / "reviews" / "test_run"
        result = save_review_bundle(
            review_dir=review_dir,
            email=email,
            phase2_json='{"note": "test"}',
            editorial_json=json.dumps(email.model_dump(mode="json"), indent=2),
            markdown="# Test markdown",
            html="<html>test</html>",
            metadata_json="[]",
            chart_fragments={},
            summary=summary,
            checklist=checklist,
        )

        assert result == review_dir / "review_checklist.md"
        assert (review_dir / "phase2_report.json").exists()
        assert (review_dir / "editorial_email.json").exists()
        assert (review_dir / "editorial_email.md").exists()
        assert (review_dir / "editorial_email.html").exists()
        assert (review_dir / "metadata.json").exists()
        assert (review_dir / "review_summary.json").exists()
        assert (review_dir / "review_checklist.md").exists()
        assert (review_dir / "charts").is_dir()

    def test_save_review_bundle_with_charts(self, tmp_path: Path) -> None:
        email = _make_email()
        summary = build_review_summary(
            email=email,
            metadata=[],
            fallback_used=False,
            news_count=10,
            snapshot_count=3,
            chart_count=1,
            ai_enabled=True,
            ai_dry_run=True,
        )
        checklist = build_review_checklist(email, summary)

        review_dir = tmp_path / "review_with_charts"
        save_review_bundle(
            review_dir=review_dir,
            email=email,
            phase2_json="{}",
            editorial_json="{}",
            markdown="# Test",
            html="<html></html>",
            metadata_json="[]",
            chart_fragments={"change_pct_bar": "<div>fake chart</div>"},
            summary=summary,
            checklist=checklist,
        )

        assert (review_dir / "charts" / "change_pct_bar.html").exists()
        content = (review_dir / "charts" / "change_pct_bar.html").read_text(encoding="utf-8")
        assert "fake chart" in content

    def test_review_summary_json_serializable(self) -> None:
        email = _make_email()
        summary = build_review_summary(
            email=email,
            metadata=_make_metadata(),
            fallback_used=False,
            news_count=10,
            snapshot_count=3,
            chart_count=2,
            ai_enabled=True,
            ai_dry_run=False,
        )
        json_str = json.dumps(summary, ensure_ascii=False, indent=2)
        parsed = json.loads(json_str)
        assert parsed["review_status"] == "pending"
        assert parsed["news_count"] == 10
