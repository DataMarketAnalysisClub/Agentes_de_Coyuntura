"""Compare fallback editorial vs IA editorial (one or more Ollama models).

This job runs the phase 3 pipeline twice (or more) on the same input and writes
side-by-side review bundles:

- fallback/  - deterministic output, always generated.
- models/<safe_model_name>/  - one per model listed in OLLAMA_COMPARE_MODELS.

A top-level comparison_report.md and comparison_summary.json make it easy to
evaluate differences without opening every JSON.

The job works even when OLLAMA_API_KEY is missing: in that case only the
fallback bundle is produced and the comparison report explains how to enable
the real model comparison.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.config import Settings, get_settings
from services.ai.editorial_pipeline import (
    Phase3PipelineResult,
    run_phase3_pipeline,
)
from services.ai.quality_score import compute_quality_score
from services.ai.review_checklist import (
    build_review_checklist,
    build_review_summary,
    save_review_bundle,
)
from services.ai.schemas import AiEditorialEmail
from storage.models import MarketSnapshot, NewsItem

logger = logging.getLogger(__name__)


_SAFE_MODEL_RE = re.compile(r"[^A-Za-z0-9._-]+")


class _RunRecord(BaseModel):
    name: str
    status: str
    quality_score: int
    chart_count: int
    section_count: int
    fallback_used: bool
    duration_ms: int
    error_message: str = ""
    ai_run_status: str = ""


@dataclass
class _BundleInputs:
    news: list[NewsItem]
    snapshots: list[MarketSnapshot]
    source_summary: dict
    input_news_json: str
    input_snapshots_json: str
    source_summary_json: str
    source_count: int


def _safe_model_name(model: str) -> str:
    cleaned = _SAFE_MODEL_RE.sub("_", model).strip("_")
    return cleaned or "model"


def _build_settings_with(
    base: Settings,
    *,
    ai_enabled: bool,
    ai_dry_run: bool,
    ollama_model: str = "",
) -> Settings:
    """Build a Settings instance with override fields.

    Pydantic v2 BaseSettings does NOT honour the cached `lru_cache` instance
    when we mutate attributes, so we return a fresh instance.
    """
    overrides: dict[str, Any] = {
        "ai_enabled": ai_enabled,
        "ai_dry_run": ai_dry_run,
    }
    if ollama_model:
        overrides["ollama_model"] = ollama_model
    return base.model_copy(update=overrides)


def _run_pipeline(
    *,
    news: list[NewsItem],
    snapshots: list[MarketSnapshot],
    settings: Settings,
) -> Phase3PipelineResult:
    return run_phase3_pipeline(
        news_items=news,
        snapshots=snapshots,
        max_news=settings.ai_max_news_items,
        max_per_group=settings.ai_max_news_per_group,
        max_groups=settings.ai_max_groups,
        render_charts_enabled=settings.ai_charts_enabled,
        max_charts=settings.ai_max_charts,
        settings=settings,
    )


def _serialize_news(news: list[NewsItem]) -> str:
    items = [
        {
            "timestamp": n.timestamp.isoformat() if n.timestamp else None,
            "source": n.source, "title": n.title, "url": n.url,
            "summary": n.summary, "region": n.region, "topic": n.topic,
            "impact_score": n.impact_score,
        }
        for n in news
    ]
    return json.dumps(items, ensure_ascii=False, indent=2)


def _serialize_snapshots(snapshots: list[MarketSnapshot]) -> str:
    items = [
        {
            "timestamp": s.timestamp.isoformat() if s.timestamp else None,
            "symbol": s.symbol, "name": s.name, "price": s.price,
            "change_pct": s.change_pct, "source": s.source,
        }
        for s in snapshots
    ]
    return json.dumps(items, ensure_ascii=False, indent=2)


def _build_source_summary(news: list[NewsItem]) -> dict:
    from collections import Counter

    sources = Counter(n.source for n in news)
    regions = Counter(n.region for n in news)
    topics = Counter(n.topic for n in news)
    return {
        "news_count": len(news),
        "sources": dict(sources.most_common()),
        "regions": dict(regions.most_common()),
        "topics": dict(topics.most_common()),
    }


def _bundle_inputs(
    news: list[NewsItem],
    snapshots: list[MarketSnapshot],
) -> _BundleInputs:
    source_summary = _build_source_summary(news)
    return _BundleInputs(
        news=news,
        snapshots=snapshots,
        source_summary=source_summary,
        input_news_json=_serialize_news(news),
        input_snapshots_json=_serialize_snapshots(snapshots),
        source_summary_json=json.dumps(source_summary, ensure_ascii=False, indent=2),
        source_count=len(source_summary["sources"]),
    )


def _save_variant(
    *,
    variant_dir: Path,
    result: Phase3PipelineResult,
    inputs: _BundleInputs,
    settings: Settings,
    quality_score_json: str,
) -> None:
    email = result.editorial
    if email is None:
        return
    phase2_json = (
        json.dumps(result.phase2_report.model_dump(mode="json"), ensure_ascii=False, indent=2)
        if result.phase2_report
        else json.dumps({"note": "no phase2"}, ensure_ascii=False, indent=2)
    )
    metadata_json = json.dumps(
        [m.model_dump(mode="json") for m in result.metadata],
        ensure_ascii=False, indent=2,
    )
    summary = build_review_summary(
        email=email,
        metadata=result.metadata,
        fallback_used=result.fallback_used,
        news_count=len(inputs.news),
        snapshot_count=len(inputs.snapshots),
        chart_count=len(result.chart_fragments),
        ai_enabled=settings.ai_enabled,
        ai_dry_run=settings.ai_dry_run,
        phase2_regional_reports_count=(
            len(result.phase2_report.regional_reports) if result.phase2_report else 0
        ),
        source_count=inputs.source_count,
    )
    quality_score = json.loads(quality_score_json)
    checklist = build_review_checklist(email, summary, quality_score)

    save_review_bundle(
        review_dir=variant_dir,
        email=email,
        phase2_json=phase2_json,
        editorial_json=json.dumps(
            email.model_dump(mode="json"), ensure_ascii=False, indent=2,
        ),
        markdown=result.markdown,
        html=result.html,
        metadata_json=metadata_json,
        chart_fragments=result.chart_fragments,
        summary=summary,
        checklist=checklist,
        input_news_json=inputs.input_news_json,
        input_snapshots_json=inputs.input_snapshots_json,
        source_summary_json=inputs.source_summary_json,
        quality_score_json=quality_score_json,
    )


def _quality_score_for(
    email: AiEditorialEmail,
    result: Phase3PipelineResult,
    inputs: _BundleInputs,
    settings: Settings,
) -> str:
    phase2_reg_count = (
        len(result.phase2_report.regional_reports) if result.phase2_report else 0
    )
    score = compute_quality_score(
        email=email,
        news_count=len(inputs.news),
        phase2_regional_reports_count=phase2_reg_count,
        source_count=inputs.source_count,
        chart_count=len(result.chart_fragments),
        snapshots=inputs.snapshots,
        news=inputs.news,
        fallback_used=result.fallback_used,
    )
    return json.dumps(score, ensure_ascii=False, indent=2)


def _run_variant(
    *,
    name: str,
    variant_dir: Path,
    inputs: _BundleInputs,
    settings: Settings,
    records: list[_RunRecord],
) -> Phase3PipelineResult | None:
    start = time.monotonic()
    try:
        result = _run_pipeline(news=inputs.news, snapshots=inputs.snapshots, settings=settings)
    except Exception as e:  # noqa: BLE001 - we want to record any failure
        duration_ms = int((time.monotonic() - start) * 1000)
        records.append(_RunRecord(
            name=name, status="error",
            quality_score=0, chart_count=0, section_count=0,
            fallback_used=False, duration_ms=duration_ms,
            error_message=str(e),
            ai_run_status="pipeline_error",
        ))
        logger.warning("Variant %s failed: %s", name, e)
        return None

    duration_ms = int((time.monotonic() - start) * 1000)
    email = result.editorial
    if email is None:
        records.append(_RunRecord(
            name=name, status="empty",
            quality_score=0, chart_count=0, section_count=0,
            fallback_used=result.fallback_used, duration_ms=duration_ms,
            error_message="Pipeline returned no editorial",
            ai_run_status="empty_pipeline",
        ))
        return result

    quality_json = _quality_score_for(email, result, inputs, settings)
    quality = json.loads(quality_json)

    _save_variant(
        variant_dir=variant_dir,
        result=result,
        inputs=inputs,
        settings=settings,
        quality_score_json=quality_json,
    )

    records.append(_RunRecord(
        name=name, status="ok",
        quality_score=quality["score"],
        chart_count=len(result.chart_fragments),
        section_count=len(email.sections),
        fallback_used=result.fallback_used,
        duration_ms=duration_ms,
        ai_run_status="ok" if not result.fallback_used else "fallback_used",
    ))
    return result


def _models_to_compare(base: Settings) -> list[str]:
    raw = os.getenv("OLLAMA_COMPARE_MODELS", "").strip()
    if raw:
        return [m.strip() for m in raw.split(",") if m.strip()]
    if base.ollama_model:
        return [base.ollama_model]
    return []


def _build_comparison_report(
    base_dir: Path,
    records: list[_RunRecord],
    inputs: _BundleInputs,
    ai_ready: bool,
) -> str:
    lines: list[str] = []
    lines.append("# Comparacion Editorial: Fallback vs IA")
    lines.append("")
    lines.append(f"Generado: {datetime.now(UTC).isoformat()}")
    lines.append(f"Noticias input: {inputs.source_summary.get('news_count', 0)}")
    lines.append(f"Fuentes: {inputs.source_count}")
    lines.append("")

    lines.append("## Estado")
    lines.append(f"- Fallback generado: {'si' if any(r.name == 'fallback' for r in records) else 'no'}")
    lines.append(f"- IA ejecutada: {'si' if any(r.name.startswith('model:') for r in records) else 'no'}")
    if not ai_ready:
        lines.append("- Motivo IA no ejecutada: falta OLLAMA_API_KEY o AI_DRY_RUN=true.")
    lines.append("")

    lines.append("## Puntajes por variante")
    lines.append("")
    lines.append("| Variante | Status | Score | Charts | Secciones | Fallback | Duracion (ms) |")
    lines.append("|----------|--------|------:|-------:|----------:|----------|--------------:|")
    for r in records:
        lines.append(
            f"| {r.name} | {r.status} | {r.quality_score} | {r.chart_count} | "
            f"{r.section_count} | {r.fallback_used} | {r.duration_ms} |"
        )
    lines.append("")

    if any(r.name.startswith("model:") for r in records):
        lines.append("## Diferencias Editoriales")
        lines.append("- Revisa manualmente editorial_email.md de cada variante.")
        lines.append("- Compara `subject`, `headline`, `preheader` y bullets clave.")
        lines.append("- Comcaution count y source_notes.")
        lines.append("")

    lines.append("## Decision")
    lines.append("- [ ] Usar fallback como base.")
    lines.append("- [ ] Usar IA como base.")
    lines.append("- [ ] Usar IA solo para narrativa y fallback para trazabilidad.")
    lines.append("- [ ] Ajustar prompts.")
    lines.append("- [ ] Probar con otro modelo.")
    lines.append("")

    lines.append("## Como habilitar comparacion IA real")
    lines.append("")
    lines.append("1. Configura `OLLAMA_API_KEY` con una key valida de Ollama Cloud.")
    lines.append("2. Asegurate de que `AI_DRY_RUN=false` y `AI_ENABLED=true`.")
    lines.append("3. Opcional: define `OLLAMA_COMPARE_MODELS=gpt-oss:120b,otro-modelo`.")
    lines.append("4. Vuelve a ejecutar `python -m app.main ai-review-compare`.")
    lines.append("")
    return "\n".join(lines)


def _run_mock_dataset() -> tuple[list[MarketSnapshot], list[NewsItem]]:
    from jobs.ai_review_fast import _build_mock_dataset

    return _build_mock_dataset()


def run_ai_review_compare(
    news: list[NewsItem] | None = None,
    snapshots: list[MarketSnapshot] | None = None,
    *,
    use_mock: bool | None = None,
) -> Path | None:
    """Run the editorial comparison job.

    By default, uses the real news + snapshots pipeline unless `use_mock=True`
    is passed. When neither is given, fetches via `collect_market_and_news`.
    """
    base = get_settings()

    if use_mock is None:
        env_flag = os.getenv("AI_COMPARE_USE_MOCK", "").strip().lower()
        use_mock = env_flag in {"1", "true", "yes"}

    if (news is None or snapshots is None):
        if use_mock:
            snapshots, news = _run_mock_dataset()
        else:
            from jobs.common import collect_market_and_news

            snapshots, news = collect_market_and_news(news_hours=18)

    stem = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_dir = Path(base.ai_output_dir) / "compare_reviews" / stem
    base_dir.mkdir(parents=True, exist_ok=True)

    inputs = _bundle_inputs(news, snapshots)
    (base_dir / "input_news.json").write_text(inputs.input_news_json, encoding="utf-8")
    (base_dir / "input_snapshots.json").write_text(inputs.input_snapshots_json, encoding="utf-8")
    (base_dir / "source_summary.json").write_text(inputs.source_summary_json, encoding="utf-8")

    records: list[_RunRecord] = []

    fallback_settings = _build_settings_with(
        base, ai_enabled=False, ai_dry_run=True,
    )
    fallback_dir = base_dir / "fallback"
    fallback_dir.mkdir(parents=True, exist_ok=True)
    _run_variant(
        name="fallback", variant_dir=fallback_dir,
        inputs=inputs, settings=fallback_settings, records=records,
    )

    ai_ready = bool(base.ollama_api_key) and not base.ai_dry_run
    if not ai_ready:
        reason = (
            "OLLAMA_API_KEY vacia" if not base.ollama_api_key
            else "AI_DRY_RUN=true"
        )
        logger.info("Skipping IA variants: %s", reason)
        records.append(_RunRecord(
            name="models", status="skipped",
            quality_score=0, chart_count=0, section_count=0,
            fallback_used=False, duration_ms=0,
            error_message=f"IA no ejecutada ({reason}).",
            ai_run_status="missing_ollama_api_key" if not base.ollama_api_key else "dry_run_active",
        ))
    else:
        for model in _models_to_compare(base):
            model_settings = _build_settings_with(
                base,
                ai_enabled=True,
                ai_dry_run=False,
                ollama_model=model,
            )
            variant_dir = base_dir / "models" / _safe_model_name(model)
            variant_dir.mkdir(parents=True, exist_ok=True)
            _run_variant(
                name=f"model:{model}", variant_dir=variant_dir,
                inputs=inputs, settings=model_settings, records=records,
            )

    summary = {
        "generated_at": datetime.now(UTC).isoformat(),
        "use_mock": use_mock,
        "news_count": len(news),
        "snapshot_count": len(snapshots),
        "source_count": inputs.source_count,
        "fallback_ready": any(r.name == "fallback" and r.status == "ok" for r in records),
        "ai_ready": ai_ready,
        "models_requested": _models_to_compare(base),
        "variants": [r.model_dump() for r in records],
    }
    (base_dir / "comparison_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    report = _build_comparison_report(base_dir, records, inputs, ai_ready)
    (base_dir / "comparison_report.md").write_text(report, encoding="utf-8")

    print(f"\nComparison bundle saved to: {base_dir}")
    print(f"Report: {base_dir / 'comparison_report.md'}")
    print(f"Fallback: {summary['fallback_ready']}")
    print(f"IA executed: {ai_ready}")
    for r in records:
        print(f"  - {r.name}: {r.status} (score={r.quality_score})")

    if not ai_ready:
        print("Set OLLAMA_API_KEY and AI_DRY_RUN=false to run model comparison.")

    return base_dir
