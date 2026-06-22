"""Manual job to run the phase 2 AI pipeline and save outputs to disk."""

import json
import logging
from datetime import datetime
from pathlib import Path

from app.config import get_settings
from jobs.common import collect_market_and_news
from services.ai.pipeline import run_phase2_pipeline

logger = logging.getLogger(__name__)


def run_ai_phase2_report(news_hours: int = 18) -> Path | None:
    """Collect news, run phase 2 pipeline, and save report to outputs/ai/.

    Does NOT send emails or replace the productive brief.
    """
    settings = get_settings()

    snapshots, scored_news = collect_market_and_news(news_hours=news_hours)
    logger.info(
        "Phase 2 input ready",
        extra={"snapshots": len(snapshots), "news": len(scored_news)},
    )

    result = run_phase2_pipeline(
        news_items=scored_news,
        snapshots=snapshots,
        max_news=settings.ai_max_news_items,
        max_per_group=settings.ai_max_news_per_group,
        max_groups=settings.ai_max_groups,
    )

    if result.report is None:
        logger.warning("Phase 2 pipeline produced no report")
        return None

    output_dir = Path(settings.ai_output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    stem = datetime.now().strftime("%Y%m%d_%H%M")
    json_path = output_dir / f"{stem}_phase2_report.json"
    md_path = output_dir / f"{stem}_phase2_report.md"

    report_json = result.report.model_dump(mode="json")
    json_path.write_text(
        json.dumps(report_json, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    md_path.write_text(_report_to_markdown(result.report), encoding="utf-8")

    metadata_path = output_dir / f"{stem}_phase2_metadata.json"
    metadata_path.write_text(
        json.dumps(
            [m.model_dump(mode="json") for m in result.all_metadata],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    logger.info(
        "Phase 2 report saved",
        extra={
            "json": str(json_path),
            "markdown": str(md_path),
            "metadata": str(metadata_path),
            "regional_reports": len(result.report.regional_reports),
        },
    )

    return json_path


def _report_to_markdown(report) -> str:  # type: ignore[no-untyped-def]
    """Render an AiPhase2Report as markdown text."""
    lines: list[str] = []
    lines.append(f"# Reporte Intermedio Fase 2 - {report.generated_at.isoformat()}")
    lines.append("")

    if report.global_summary:
        lines.append("## Resumen Global")
        for point in report.global_summary:
            lines.append(f"- {point}")
        lines.append("")

    for regional in report.regional_reports:
        label = regional.country or regional.region
        lines.append(f"## {label}")
        if regional.executive_summary:
            for point in regional.executive_summary:
                lines.append(f"- {point}")
        for cluster in regional.topic_clusters:
            lines.append(f"### Topic: {cluster.topic} ({cluster.relevance})")
            if cluster.observed_facts:
                lines.append("**Hechos:**")
                for fact in cluster.observed_facts:
                    lines.append(f"- {fact}")
            if cluster.interpretation:
                lines.append("**Interpretacion preliminar:**")
                for interp in cluster.interpretation:
                    lines.append(f"- {interp}")
            if cluster.affected_assets:
                lines.append(f"**Activos relacionados:** {', '.join(cluster.affected_assets)}")
            if cluster.watch_items:
                lines.append("**A vigilar:**")
                for item in cluster.watch_items:
                    lines.append(f"- {item}")
            lines.append("")

    if report.editorial_cautions:
        lines.append("## Cautelas Editoriales")
        for caution in report.editorial_cautions:
            lines.append(f"- {caution}")
        lines.append("")

    lines.append("---")
    lines.append("*Reporte intermedio. No constituye recomendacion de inversion.*")

    return "\n".join(lines)
