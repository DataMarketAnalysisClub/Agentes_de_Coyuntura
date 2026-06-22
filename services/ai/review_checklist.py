"""Generate an editorial review checklist for a phase 3 editorial email sample.

The checklist is a markdown file with MVP review criteria grouped by category.
It also includes a summary of the run (fallback used, news count, chart count,
known issues) so the reviewer can quickly assess what they are looking at.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from services.ai.schemas import AiEditorialEmail


def build_review_summary(
    email: AiEditorialEmail,
    metadata: list,
    fallback_used: bool,
    news_count: int,
    snapshot_count: int,
    chart_count: int,
    ai_enabled: bool,
    ai_dry_run: bool,
    phase2_regional_reports_count: int = 0,
    source_count: int = 0,
) -> dict:
    """Build a JSON-serializable summary of the review run."""
    validation_statuses = []
    for m in metadata:
        status = getattr(m, "validation_status", None)
        stage = getattr(m, "stage", None)
        if status and stage:
            validation_statuses.append({"stage": stage, "status": status})

    return {
        "review_status": "pending",
        "generated_at": datetime.now(UTC).isoformat(),
        "fallback_used": fallback_used,
        "ai_enabled": ai_enabled,
        "ai_dry_run": ai_dry_run,
        "news_count": news_count,
        "snapshot_count": snapshot_count,
        "chart_count": chart_count,
        "section_count": len(email.sections),
        "executive_summary_points": len(email.executive_summary),
        "caution_count": len(email.editorial_cautions),
        "phase2_regional_reports_count": phase2_regional_reports_count,
        "source_count": source_count,
        "validation_statuses": validation_statuses,
        "known_issues": _detect_known_issues(
            email, fallback_used, news_count, phase2_regional_reports_count, source_count,
        ),
    }


def build_review_checklist(
    email: AiEditorialEmail,
    summary: dict,
    quality_score: dict | None = None,
) -> str:
    """Build the review checklist as a markdown string."""
    lines: list[str] = []
    lines.append("# Checklist Revision Editorial")
    lines.append("")
    lines.append(f"Generado: {summary['generated_at']}")
    lines.append("")

    lines.append("## Resumen de la corrida")
    lines.append("")
    lines.append(f"- **Fallback usado:** {summary['fallback_used']}")
    lines.append(f"- **IA habilitada:** {summary['ai_enabled']}")
    lines.append(f"- **Dry run:** {summary['ai_dry_run']}")
    lines.append(f"- **Noticias input:** {summary['news_count']}")
    lines.append(f"- **Snapshots input:** {summary['snapshot_count']}")
    lines.append(f"- **Graficos renderizados:** {summary['chart_count']}")
    lines.append(f"- **Secciones:** {summary['section_count']}")
    lines.append(f"- **Cautelas editoriales:** {summary['caution_count']}")
    lines.append("")

    if quality_score is not None:
        lines.append("## Quality Score (MVP)")
        lines.append("")
        lines.append(f"**Score total:** {quality_score['score']}/100")
        lines.append("")
        lines.append("Checks individuales (10 pts c/u):")
        lines.append("")
        for check_name, passed in quality_score["checks"].items():
            mark = "[x]" if passed else "[ ]"
            lines.append(f"- {mark} {check_name}")
        lines.append("")

    if summary["known_issues"]:
        lines.append("## Problemas detectados automaticamente")
        lines.append("")
        for issue in summary["known_issues"]:
            lines.append(f"- {issue}")
        lines.append("")

    lines.append("## Claridad")
    lines.append("- [ ] El asunto es claro y factual (max 80 caracteres).")
    lines.append("- [ ] El headline resume bien la coyuntura.")
    lines.append("- [ ] El resumen ejecutivo tiene 2-4 puntos utiles.")
    lines.append("- [ ] El preheader es breve y informativo.")
    lines.append("")

    lines.append("## Trazabilidad")
    lines.append("- [ ] Cada interpretacion esta respaldada por hechos/noticias.")
    lines.append("- [ ] No hay datos inventados.")
    lines.append("- [ ] No hay URLs o fuentes inventadas.")
    lines.append("- [ ] Las source_notes coinciden con las fuentes reales.")
    lines.append("")

    lines.append("## Prudencia financiera")
    lines.append("- [ ] No hay recomendaciones de inversion.")
    lines.append("- [ ] Se separan hechos de interpretacion.")
    lines.append("- [ ] Hay cautelas cuando falta contexto.")
    lines.append("- [ ] No se afirman relaciones causales no respaldadas.")
    lines.append("")

    lines.append("## Estructura")
    lines.append("- [ ] Chile aparece si hay noticias chilenas relevantes.")
    lines.append("- [ ] EE.UU./Global aparecen si dominan el flujo.")
    lines.append("- [ ] Las secciones no repiten contenido.")
    lines.append("- [ ] El orden de secciones tiene sentido editorial.")
    lines.append("")

    lines.append("## Graficos")
    lines.append("- [ ] Los graficos aportan al relato.")
    lines.append("- [ ] No hay graficos redundantes.")
    lines.append("- [ ] Las etiquetas se leen bien.")
    lines.append("- [ ] Las fuentes de los graficos estan claras.")
    lines.append("- [ ] No hay mas graficos de los necesarios (max 3-4 ideal).")
    lines.append("")

    lines.append("## Decision")
    lines.append("- [ ] Aprobado para iterar.")
    lines.append("- [ ] Requiere ajuste de prompt.")
    lines.append("- [ ] Requiere ajuste de graficos.")
    lines.append("- [ ] Requiere ajuste de fuentes/datos.")
    lines.append("- [ ] Requiere ajuste de estructura/secciones.")
    lines.append("")

    lines.append("## Notas del revisor")
    lines.append("")
    lines.append("```")
    lines.append("```")
    lines.append("")

    return "\n".join(lines)


def save_review_bundle(
    review_dir: Path,
    email: AiEditorialEmail,
    phase2_json: str,
    editorial_json: str,
    markdown: str,
    html: str,
    metadata_json: str,
    chart_fragments: dict[str, str],
    summary: dict,
    checklist: str,
    input_news_json: str = "",
    input_snapshots_json: str = "",
    source_summary_json: str = "",
    quality_score_json: str = "",
) -> Path:
    """Save the full review bundle to a directory."""
    review_dir.mkdir(parents=True, exist_ok=True)
    charts_dir = review_dir / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    (review_dir / "phase2_report.json").write_text(phase2_json, encoding="utf-8")
    (review_dir / "editorial_email.json").write_text(editorial_json, encoding="utf-8")
    (review_dir / "editorial_email.md").write_text(markdown, encoding="utf-8")
    (review_dir / "editorial_email.html").write_text(html, encoding="utf-8")
    (review_dir / "metadata.json").write_text(metadata_json, encoding="utf-8")
    (review_dir / "review_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (review_dir / "review_checklist.md").write_text(checklist, encoding="utf-8")

    if input_news_json:
        (review_dir / "input_news.json").write_text(input_news_json, encoding="utf-8")
    if input_snapshots_json:
        (review_dir / "input_snapshots.json").write_text(input_snapshots_json, encoding="utf-8")
    if source_summary_json:
        (review_dir / "source_summary.json").write_text(source_summary_json, encoding="utf-8")
    if quality_score_json:
        (review_dir / "quality_score.json").write_text(quality_score_json, encoding="utf-8")

    from services.ai.chart_renderer import _wrap_standalone

    for chart_id, fragment in chart_fragments.items():
        (charts_dir / f"{chart_id}.html").write_text(
            _wrap_standalone(fragment, chart_id),
            encoding="utf-8",
        )

    return review_dir / "review_checklist.md"


def _detect_known_issues(
    email: AiEditorialEmail,
    fallback_used: bool,
    news_count: int,
    phase2_regional_reports_count: int = 0,
    source_count: int = 0,
) -> list[str]:
    """Detect obvious issues automatically."""
    issues: list[str] = []

    if fallback_used:
        issues.append("Output generado con fallback deterministico (IA no disponible o fallo).")

    if not email.executive_summary:
        issues.append("Resumen ejecutivo vacio.")

    if not email.sections:
        issues.append("No hay secciones editoriales.")

    if not email.subject.strip():
        issues.append("Asunto vacio.")

    if not email.editorial_cautions:
        issues.append("No hay cautelas editoriales.")

    if news_count == 0:
        issues.append("No hay noticias en el input.")
    else:
        if phase2_regional_reports_count == 0:
            issues.append(
                f" Hay {news_count} noticias de input pero Fase 2 no genero regional_reports "
                f"(posible perdida de RSS/scraping)."
            )
        if len(email.sections) == 0 or (
            len(email.sections) == 1 and email.sections[0].heading == "Visualizaciones"
        ):
            issues.append(
                f" Hay {news_count} noticias pero el email no tiene secciones regionales "
                f"(solo Visualizaciones o vacio)."
            )
        if source_count > 0 and not email.source_notes:
            issues.append(
                f" Hay {source_count} fuentes en el input pero source_notes esta vacio en el email."
            )

    if len(email.chart_specs) > 4:
        issues.append(f"Demasiados graficos ({len(email.chart_specs)}); considerar limitar a 3-4.")

    chart_ids_in_sections = {cid for s in email.sections for cid in s.chart_ids}
    chart_ids_in_specs = {spec.chart_id for spec in email.chart_specs}
    orphan_specs = chart_ids_in_specs - chart_ids_in_sections
    if orphan_specs:
        issues.append(f"Graficos sin seccion asignada: {', '.join(sorted(orphan_specs))}.")

    return issues
