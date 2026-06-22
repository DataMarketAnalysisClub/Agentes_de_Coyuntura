"""Phase 3 pipeline: phase2 report -> editorial writer -> charts -> email HTML.

This is a preview-only pipeline: it produces files in outputs/ai/ but does NOT
send emails or touch the productive brief pipeline. If IA is disabled or fails,
a deterministic editorial email is built from the phase 2 report (which itself
falls back to deterministic assembly when IA is unavailable).
"""

import logging
from dataclasses import dataclass, field

from app.config import Settings
from services.ai.chart_renderer import render_charts, render_charts_as_png
from services.ai.editorial_email_formatter import (
    render_editorial_email_html,
    render_editorial_email_markdown,
)
from services.ai.editorial_writer import EditorialWriterResult, run_editorial_writer
from services.ai.pipeline import run_phase2_pipeline
from services.ai.schemas import AiEditorialEmail, AiPhase2Report, AiPhase3RunResult
from storage.models import MarketSnapshot, NewsItem

logger = logging.getLogger(__name__)


@dataclass
class Phase3PipelineResult:
    editorial: AiEditorialEmail | None = None
    chart_fragments: dict[str, str] = field(default_factory=dict)
    chart_pngs: dict[str, bytes] = field(default_factory=dict)
    metadata: list = field(default_factory=list)
    html: str = ""
    markdown: str = ""
    fallback_used: bool = False
    phase2_report: AiPhase2Report | None = None
    input_news: list[NewsItem] = field(default_factory=list)
    input_snapshots: list[MarketSnapshot] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.editorial is not None


def run_phase3_pipeline(
    news_items: list[NewsItem],
    snapshots: list[MarketSnapshot] | None = None,
    max_news: int = 30,
    max_per_group: int = 10,
    max_groups: int = 6,
    render_charts_enabled: bool = True,
    max_charts: int = 4,
    settings: Settings | None = None,
) -> Phase3PipelineResult:
    """Run the full phase 3 pipeline sequentially.

    Steps:
    1. Phase 2 pipeline: produce AiPhase2Report.
    2. Editorial writer: convert report into AiEditorialEmail.
    3. Chart renderer: render chart_specs into HTML fragments.
    4. Email formatter: compose final HTML + markdown.
    """
    phase2 = run_phase2_pipeline(
        news_items=news_items,
        snapshots=snapshots,
        max_news=max_news,
        max_per_group=max_per_group,
        max_groups=max_groups,
        settings=settings,
    )
    metadata: list = list(phase2.all_metadata)

    if phase2.report is None:
        logger.warning("Phase 2 produced no report, cannot run phase 3")
        return Phase3PipelineResult(
            metadata=metadata,
            input_news=news_items,
            input_snapshots=snapshots or [],
        )

    writer_result: EditorialWriterResult = run_editorial_writer(
        phase2_report=phase2.report,
        snapshots=snapshots,
        news=news_items,
        max_charts=max_charts,
        settings=settings,
    )
    metadata.append(writer_result.metadata)

    email = writer_result.email
    if email is None:
        logger.warning("Editorial writer produced no email (IA + fallback both failed)")
        return Phase3PipelineResult(
            metadata=metadata,
            phase2_report=phase2.report,
            input_news=news_items,
            input_snapshots=snapshots or [],
        )

    chart_fragments: dict[str, str] = {}
    chart_pngs: dict[str, bytes] = {}
    if render_charts_enabled and email.chart_specs:
        chart_fragments = render_charts(
            specs=email.chart_specs,
            snapshots=snapshots,
            news=news_items,
        )
        chart_pngs = render_charts_as_png(
            specs=email.chart_specs,
            snapshots=snapshots,
            news=news_items,
        )

    html = render_editorial_email_html(email, chart_fragments)
    markdown = render_editorial_email_markdown(email)

    return Phase3PipelineResult(
        editorial=email,
        chart_fragments=chart_fragments,
        chart_pngs=chart_pngs,
        metadata=metadata,
        html=html,
        markdown=markdown,
        fallback_used=not writer_result.ok,
        phase2_report=phase2.report,
        input_news=news_items,
        input_snapshots=snapshots or [],
    )


def build_phase3_run_result(result: Phase3PipelineResult) -> AiPhase3RunResult:
    """Build an auditable AiPhase3RunResult from a Phase3PipelineResult."""
    from services.ai.schemas import AiEditorialRunMetadata

    editorial = result.editorial
    if editorial is None:
        raise ValueError("Phase 3 result has no editorial email")
    editorial_meta = next(
        (m for m in result.metadata if isinstance(m, AiEditorialRunMetadata)),
        AiEditorialRunMetadata(model="unknown"),
    )
    return AiPhase3RunResult(
        editorial=editorial,
        chart_specs=editorial.chart_specs,
        metadata=editorial_meta,
        rendered_chart_ids=list(result.chart_fragments.keys()),
        fallback_used=result.fallback_used,
    )
