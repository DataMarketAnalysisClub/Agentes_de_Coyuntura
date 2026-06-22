"""Manual job to generate a full review sample bundle for editorial review.

Produces a self-contained folder in outputs/ai/reviews/YYYYMMDD_HHMM/ with:
- input_news.json           - News items fed to the pipeline (RSS + scraping)
- input_snapshots.json      - Market snapshots fed to the pipeline
- source_summary.json       - Counts by source, region, topic
- phase2_report.json        - Full Fase 2 structured report
- editorial_email.json      - Fase 3 structured email
- editorial_email.md        - Markdown version (no charts)
- editorial_email.html      - HTML preview with charts
- metadata.json             - Audit metadata for all AI stages
- review_summary.json       - Run summary (fallback, counts, issues)
- quality_score.json        - MVP quality score (0-100) with check breakdown
- review_checklist.md       - Editorial review checklist
- charts/{chart_id}.html    - Individual chart files

Does NOT send emails or replace the productive brief.
"""

import json
import logging
from collections import Counter
from datetime import datetime
from pathlib import Path

from app.config import get_settings
from jobs.common import collect_market_and_news
from services.ai.editorial_pipeline import run_phase3_pipeline
from services.ai.quality_score import compute_quality_score
from services.ai.review_checklist import (
    build_review_checklist,
    build_review_summary,
    save_review_bundle,
)

logger = logging.getLogger(__name__)


def run_ai_review_sample(news_hours: int = 18) -> Path | None:
    """Collect news, run phase 3 pipeline, and save a review bundle to disk."""
    settings = get_settings()

    snapshots, scored_news = collect_market_and_news(news_hours=news_hours)
    logger.info(
        "Review sample input ready",
        extra={"snapshots": len(snapshots), "news": len(scored_news)},
    )

    result = run_phase3_pipeline(
        news_items=scored_news,
        snapshots=snapshots,
        max_news=settings.ai_max_news_items,
        max_per_group=settings.ai_max_news_per_group,
        max_groups=settings.ai_max_groups,
        render_charts_enabled=settings.ai_charts_enabled,
        max_charts=settings.ai_max_charts,
    )

    if result.editorial is None:
        logger.warning("Review sample: pipeline produced no editorial email")
        return None

    stem = datetime.now().strftime("%Y%m%d_%H%M")
    base_dir = Path(settings.ai_output_dir)
    review_dir = base_dir / "reviews" / stem

    metadata_json = json.dumps(
        [m.model_dump(mode="json") for m in result.metadata],
        ensure_ascii=False,
        indent=2,
    )

    phase2_json = _build_phase2_json(result.phase2_report)
    input_news_json = _serialize_news(result.input_news)
    input_snapshots_json = _serialize_snapshots(result.input_snapshots)
    source_summary = _build_source_summary(result.input_news)

    phase2_regional_reports_count = (
        len(result.phase2_report.regional_reports) if result.phase2_report else 0
    )
    source_count = len(source_summary["sources"])

    quality_score = compute_quality_score(
        email=result.editorial,
        news_count=len(scored_news),
        phase2_regional_reports_count=phase2_regional_reports_count,
        source_count=source_count,
        chart_count=len(result.chart_fragments),
        snapshots=snapshots,
        news=scored_news,
        fallback_used=result.fallback_used,
    )

    summary = build_review_summary(
        email=result.editorial,
        metadata=result.metadata,
        fallback_used=result.fallback_used,
        news_count=len(scored_news),
        snapshot_count=len(snapshots),
        chart_count=len(result.chart_fragments),
        ai_enabled=settings.ai_enabled,
        ai_dry_run=settings.ai_dry_run,
        phase2_regional_reports_count=phase2_regional_reports_count,
        source_count=source_count,
    )

    checklist = build_review_checklist(result.editorial, summary, quality_score)

    checklist_path = save_review_bundle(
        review_dir=review_dir,
        email=result.editorial,
        phase2_json=phase2_json,
        editorial_json=json.dumps(
            result.editorial.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        ),
        markdown=result.markdown,
        html=result.html,
        metadata_json=metadata_json,
        chart_fragments=result.chart_fragments,
        summary=summary,
        checklist=checklist,
        input_news_json=input_news_json,
        input_snapshots_json=input_snapshots_json,
        source_summary_json=json.dumps(source_summary, ensure_ascii=False, indent=2),
        quality_score_json=json.dumps(quality_score, ensure_ascii=False, indent=2),
    )

    logger.info(
        "Review sample saved",
        extra={
            "review_dir": str(review_dir),
            "checklist": str(checklist_path),
            "charts": len(result.chart_fragments),
            "fallback_used": result.fallback_used,
            "known_issues": len(summary["known_issues"]),
            "quality_score": quality_score["score"],
        },
    )

    print(f"\nReview bundle saved to: {review_dir}")
    print(f"Checklist: {checklist_path}")
    print(f"News input: {len(scored_news)}")
    print(f"Charts: {len(result.chart_fragments)}")
    print(f"Fallback used: {result.fallback_used}")
    print(f"Quality score: {quality_score['score']}/100")
    if summary["known_issues"]:
        print(f"Known issues ({len(summary['known_issues'])}):")
        for issue in summary["known_issues"]:
            print(f"  - {issue}")

    return checklist_path


def _build_phase2_json(report) -> str:
    """Serialize the full phase 2 report to JSON."""
    if report is None:
        return json.dumps({"note": "No phase 2 report available"}, ensure_ascii=False, indent=2)
    return json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2)


def _serialize_news(news: list) -> str:
    """Serialize news items to JSON for the review bundle."""
    items = []
    for n in news:
        items.append({
            "timestamp": n.timestamp.isoformat() if n.timestamp else None,
            "source": n.source,
            "title": n.title,
            "url": n.url,
            "summary": n.summary,
            "region": n.region,
            "topic": n.topic,
            "impact_score": n.impact_score,
        })
    return json.dumps(items, ensure_ascii=False, indent=2)


def _serialize_snapshots(snapshots: list) -> str:
    """Serialize market snapshots to JSON for the review bundle."""
    items = []
    for s in snapshots:
        items.append({
            "timestamp": s.timestamp.isoformat() if s.timestamp else None,
            "symbol": s.symbol,
            "name": s.name,
            "price": s.price,
            "change_pct": s.change_pct,
            "source": s.source,
        })
    return json.dumps(items, ensure_ascii=False, indent=2)


def _build_source_summary(news: list) -> dict:
    """Build a summary of news counts by source, region, and topic."""
    sources = Counter(n.source for n in news)
    regions = Counter(n.region for n in news)
    topics = Counter(n.topic for n in news)
    return {
        "news_count": len(news),
        "sources": dict(sources.most_common()),
        "regions": dict(regions.most_common()),
        "topics": dict(topics.most_common()),
    }
