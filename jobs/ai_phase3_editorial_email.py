"""Manual job to run the phase 3 editorial email pipeline and save outputs.

Produces files in outputs/ai/:
- YYYYMMDD_HHMM_editorial_email.json   - structured AiEditorialEmail
- YYYYMMDD_HHMM_editorial_email.md     - markdown version (no charts)
- YYYYMMDD_HHMM_editorial_email.html   - standalone HTML preview (with charts)
- YYYYMMDD_HHMM_editorial_metadata.json - audit metadata for all stages
- charts/{chart_id}.html               - standalone chart files

Does NOT send emails or replace the productive brief.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from app.config import get_settings
from jobs.common import collect_market_and_news
from services.ai.editorial_pipeline import run_phase3_pipeline

logger = logging.getLogger(__name__)


def run_ai_phase3_editorial_email(news_hours: int = 18) -> Path | None:
    """Collect news, run phase 3 pipeline, and save editorial email preview to disk."""
    settings = get_settings()

    snapshots, scored_news = collect_market_and_news(news_hours=news_hours)
    logger.info(
        "Phase 3 input ready",
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
        logger.warning("Phase 3 pipeline produced no editorial email")
        return None

    output_dir = Path(settings.ai_output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    charts_dir = output_dir / "charts"

    stem = datetime.now().strftime("%Y%m%d_%H%M")

    json_path = output_dir / f"{stem}_editorial_email.json"
    md_path = output_dir / f"{stem}_editorial_email.md"
    html_path = output_dir / f"{stem}_editorial_email.html"
    metadata_path = output_dir / f"{stem}_editorial_metadata.json"

    json_path.write_text(
        json.dumps(result.editorial.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    md_path.write_text(result.markdown, encoding="utf-8")
    html_path.write_text(result.html, encoding="utf-8")
    metadata_path.write_text(
        json.dumps(
            [m.model_dump(mode="json") for m in result.metadata],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    for chart_id, fragment in result.chart_fragments.items():
        from services.ai.chart_renderer import _wrap_standalone
        (charts_dir / f"{chart_id}.html").write_text(
            _wrap_standalone(fragment, chart_id),
            encoding="utf-8",
        )

    logger.info(
        "Phase 3 editorial email saved",
        extra={
            "json": str(json_path),
            "markdown": str(md_path),
            "html": str(html_path),
            "metadata": str(metadata_path),
            "charts": len(result.chart_fragments),
            "fallback_used": result.fallback_used,
        },
    )

    return html_path
