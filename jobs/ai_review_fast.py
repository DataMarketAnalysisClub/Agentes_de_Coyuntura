"""Fast review job: runs phase 3 with a small fixed mock dataset.

Useful for quick iteration on prompts, chart styles, and editorial formatting
without waiting on real RSS/scraping or yfinance calls.
"""

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from app.config import get_settings
from services.ai.editorial_pipeline import run_phase3_pipeline
from services.ai.quality_score import compute_quality_score
from services.ai.review_checklist import (
    build_review_checklist,
    build_review_summary,
    save_review_bundle,
)
from storage.models import MarketSnapshot, NewsItem

logger = logging.getLogger(__name__)


def _build_mock_dataset() -> tuple[list[MarketSnapshot], list[NewsItem]]:
    """Build a small, realistic mock dataset for fast iteration."""
    now = datetime.now(UTC)
    news = [
        NewsItem(
            timestamp=now, source="Federal Reserve",
            title="Fed cut rates by 25bps amid cooling inflation",
            url="https://example.com/fed-1",
            summary="The Federal Reserve cut its benchmark rate by 25 basis points.",
            region="EE.UU.", topic="bancos centrales", impact_score=9,
        ),
        NewsItem(
            timestamp=now, source="Ministerio de Hacienda",
            title="Hacienda fija trayectoria fiscal para 2026",
            url="https://example.com/hacienda-1",
            summary="Politica fiscal anunciada para 2026.",
            region="Chile", topic="politica fiscal", impact_score=8,
        ),
        NewsItem(
            timestamp=now, source="ECB",
            title="ECB holds rates steady, signals patience",
            url="https://example.com/ecb-1",
            summary="ECB mantiene tasas y senala paciencia.",
            region="Eurozona", topic="bancos centrales", impact_score=7,
        ),
        NewsItem(
            timestamp=now, source="MarketWatch",
            title="Copper prices surge 3% on China demand hopes",
            url="https://example.com/copper-1",
            summary="Copper rally on China demand data.",
            region="Global", topic="commodities", impact_score=6,
        ),
        NewsItem(
            timestamp=now, source="La Tercera Pulso",
            title="Banco Central de Chile mantiene TPM en 5.5%",
            url="https://example.com/bcch-1",
            summary="BCCh mantiene tasa de politica monetaria.",
            region="Chile", topic="bancos centrales", impact_score=7,
        ),
        NewsItem(
            timestamp=now, source="Investing.com",
            title="USD/CLP rises above 900 on dollar strength",
            url="https://example.com/usdclp-1",
            summary="Dolar sube frente al peso chileno.",
            region="Chile", topic="forex", impact_score=6,
        ),
        NewsItem(
            timestamp=now, source="Financial Times",
            title="Global stocks mixed as investors weigh rate paths",
            url="https://example.com/ft-1",
            summary="Bolsas globales mixtas por trayectoria de tasas.",
            region="Global", topic="mercados", impact_score=5,
        ),
    ]
    snaps = [
        MarketSnapshot(timestamp=now, symbol="USDCLP", name="USD/CLP", price=902.5, change_pct=1.5, source="yfinance"),
        MarketSnapshot(timestamp=now, symbol="IPSA", name="IPSA", price=5230.4, change_pct=-0.3, source="yfinance"),
        MarketSnapshot(timestamp=now, symbol="COPPER", name="Cobre", price=4.52, change_pct=3.0, source="yfinance"),
        MarketSnapshot(timestamp=now, symbol="SP500", name="S&P 500", price=5980.0, change_pct=0.5, source="yfinance"),
    ]
    return snaps, news


def run_ai_review_fast() -> Path | None:
    """Run phase 3 with a fixed mock dataset and save a review bundle."""
    settings = get_settings()
    snapshots, news = _build_mock_dataset()

    logger.info(
        "Fast review with mock dataset",
        extra={"snapshots": len(snapshots), "news": len(news)},
    )

    result = run_phase3_pipeline(
        news_items=news,
        snapshots=snapshots,
        max_news=settings.ai_max_news_items,
        max_per_group=settings.ai_max_news_per_group,
        max_groups=settings.ai_max_groups,
        render_charts_enabled=settings.ai_charts_enabled,
        max_charts=settings.ai_max_charts,
    )

    if result.editorial is None:
        logger.warning("Fast review: pipeline produced no editorial email")
        return None

    stem = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_dir = Path(settings.ai_output_dir)
    review_dir = base_dir / "fast_reviews" / stem

    metadata_json = json.dumps(
        [m.model_dump(mode="json") for m in result.metadata],
        ensure_ascii=False,
        indent=2,
    )

    phase2_json = (
        json.dumps(result.phase2_report.model_dump(mode="json"), ensure_ascii=False, indent=2)
        if result.phase2_report
        else json.dumps({"note": "no phase2"}, ensure_ascii=False, indent=2)
    )

    input_news_json = json.dumps(
        [
            {
                "timestamp": n.timestamp.isoformat(),
                "source": n.source, "title": n.title, "url": n.url,
                "summary": n.summary, "region": n.region, "topic": n.topic,
                "impact_score": n.impact_score,
            }
            for n in news
        ],
        ensure_ascii=False, indent=2,
    )
    input_snapshots_json = json.dumps(
        [
            {
                "timestamp": s.timestamp.isoformat(),
                "symbol": s.symbol, "name": s.name, "price": s.price,
                "change_pct": s.change_pct, "source": s.source,
            }
            for s in snapshots
        ],
        ensure_ascii=False, indent=2,
    )
    source_summary = {
        "news_count": len(news),
        "sources": dict(sorted(
            {n.source: sum(1 for x in news if x.source == n.source) for n in news}.items()
        )),
        "regions": dict(sorted(
            {n.region: sum(1 for x in news if x.region == n.region) for n in news}.items()
        )),
        "topics": dict(sorted(
            {n.topic: sum(1 for x in news if x.topic == n.topic) for n in news}.items()
        )),
    }
    source_summary_json = json.dumps(source_summary, ensure_ascii=False, indent=2)

    phase2_reg_count = (
        len(result.phase2_report.regional_reports) if result.phase2_report else 0
    )
    source_count = len(source_summary["sources"])

    quality_score = compute_quality_score(
        email=result.editorial,
        news_count=len(news),
        phase2_regional_reports_count=phase2_reg_count,
        source_count=source_count,
        chart_count=len(result.chart_fragments),
        snapshots=snapshots,
        news=news,
        fallback_used=result.fallback_used,
    )

    summary = build_review_summary(
        email=result.editorial,
        metadata=result.metadata,
        fallback_used=result.fallback_used,
        news_count=len(news),
        snapshot_count=len(snapshots),
        chart_count=len(result.chart_fragments),
        ai_enabled=settings.ai_enabled,
        ai_dry_run=settings.ai_dry_run,
        phase2_regional_reports_count=phase2_reg_count,
        source_count=source_count,
    )

    checklist = build_review_checklist(result.editorial, summary, quality_score)

    checklist_path = save_review_bundle(
        review_dir=review_dir,
        email=result.editorial,
        phase2_json=phase2_json,
        editorial_json=json.dumps(
            result.editorial.model_dump(mode="json"), ensure_ascii=False, indent=2,
        ),
        markdown=result.markdown,
        html=result.html,
        metadata_json=metadata_json,
        chart_fragments=result.chart_fragments,
        summary=summary,
        checklist=checklist,
        input_news_json=input_news_json,
        input_snapshots_json=input_snapshots_json,
        source_summary_json=source_summary_json,
        quality_score_json=json.dumps(quality_score, ensure_ascii=False, indent=2),
    )

    print(f"\nFast review bundle saved to: {review_dir}")
    print(f"Checklist: {checklist_path}")
    print(f"News: {len(news)}, Charts: {len(result.chart_fragments)}")
    print(f"Fallback: {result.fallback_used}")
    print(f"Quality score: {quality_score['score']}/100")
    return checklist_path
