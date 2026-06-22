"""Phase 2 pipeline: macro router -> topic router -> intermediate report."""

import json
import logging
from collections import defaultdict
from datetime import UTC, datetime

from pydantic import ValidationError

from app.config import Settings
from services.ai.grouping import group_by_country
from services.ai.json_validation import JsonValidationError, validate_response
from services.ai.macro_router import MacroRouterResult, news_for_group, run_macro_router
from services.ai.ollama_client import OllamaCloudClient, OllamaCloudError
from services.ai.prompt_loader import load_prompt
from services.ai.schemas import (
    AiIntermediateRegionalReport,
    AiPhase2Report,
    AiPhase2RunMetadata,
    AiRoutedNewsInput,
    AiTopicCluster,
    AiTopicRouterResponse,
)
from services.ai.topic_router import TopicRouterResult, run_topic_router
from storage.models import MarketSnapshot, NewsItem

logger = logging.getLogger(__name__)


class Phase2PipelineResult:
    def __init__(
        self,
        report: AiPhase2Report | None,
        metadata_list: list[AiPhase2RunMetadata],
    ) -> None:
        self.report = report
        self.metadata_list = metadata_list

    @property
    def ok(self) -> bool:
        return self.report is not None

    @property
    def all_metadata(self) -> list[AiPhase2RunMetadata]:
        return self.metadata_list


def run_phase2_pipeline(
    news_items: list[NewsItem],
    snapshots: list[MarketSnapshot] | None = None,
    max_news: int = 30,
    max_per_group: int = 10,
    max_groups: int = 6,
    settings: Settings | None = None,
) -> Phase2PipelineResult:
    """Run the full phase 2 pipeline sequentially.

    Steps:
    1. Macro router: group news by region/country.
    2. Topic router: for each macro group, group by topic.
    3. Intermediate report: consolidate into AiPhase2Report.
    """
    all_metadata: list[AiPhase2RunMetadata] = []

    # Step 1: Macro router
    macro_result = run_macro_router(news_items, snapshots, max_news=max_news, settings=settings)
    all_metadata.append(macro_result.metadata)

    if not macro_result.ok or not macro_result.response or not macro_result.response.groups:
        logger.warning("Macro router did not produce valid groups, building deterministic fallback report")
        return Phase2PipelineResult(
            report=_build_deterministic_fallback(macro_result, max_groups=max_groups),
            metadata_list=all_metadata,
        )

    # Step 2: Topic router per macro group
    topic_responses: list[tuple[str, str | None, AiTopicRouterResponse]] = []
    groups = macro_result.response.groups[:max_groups] if macro_result.response else []

    for group in groups:
        region_label = group.country or group.region
        group_news = news_for_group(macro_result.routed_news, group.news_urls)

        if not group_news:
            logger.info("No news for group %s, skipping topic router", region_label)
            continue

        topic_result: TopicRouterResult = run_topic_router(
            group_news,
            snapshots,
            region_label,
            max_per_group=max_per_group,
            settings=settings,
        )
        all_metadata.append(topic_result.metadata)

        if topic_result.ok and topic_result.response:
            topic_responses.append((group.region, group.country, topic_result.response))
        else:
            logger.warning("Topic router failed for %s, continuing", region_label)

    # Step 3: Intermediate report
    report = _build_intermediate_report(
        macro_result=macro_result,
        topic_responses=topic_responses,
        all_metadata=all_metadata,
    )

    return Phase2PipelineResult(report=report, metadata_list=all_metadata)


def _build_deterministic_fallback(
    macro_result: MacroRouterResult,
    max_groups: int = 6,
) -> AiPhase2Report:
    """Build a deterministic fallback report using routed_news when IA fails.

    Groups news by country (or region as fallback), creates macro groups and
    topic clusters deterministically from the actual RSS/scraping data.
    """
    routed = macro_result.routed_news
    if not routed:
        return AiPhase2Report(
            status="ok",
            generated_at=datetime.now(UTC),
            regional_reports=[],
            global_summary=[],
            editorial_cautions=[
                "Reporte intermedio generado como fallback: no hay noticias de input.",
            ],
        )

    by_country = group_by_country(routed)
    regional_reports: list[AiIntermediateRegionalReport] = []
    global_high_impact: list[str] = []

    sorted_groups = sorted(
        by_country.items(),
        key=lambda kv: (max(n.impact_score for n in kv[1]) if kv[1] else 0),
        reverse=True,
    )[:max_groups]

    for label, items in sorted_groups:
        country = label if any(it.country == label for it in items) else None
        region = items[0].region if items else label

        topic_clusters = _build_deterministic_topic_clusters(items, region, country)
        executive_summary = _build_deterministic_executive_summary(items)
        cautions = _build_deterministic_cautions(items, label)

        for it in items:
            if it.impact_score >= 8:
                global_high_impact.append(f"[{label}] {it.title}")

        regional_reports.append(AiIntermediateRegionalReport(
            region=region,
            country=country,
            executive_summary=executive_summary,
            topic_clusters=topic_clusters,
            cross_asset_links=[],
            watchlist=[],
            cautions=cautions,
        ))

    global_summary = global_high_impact[:5] if global_high_impact else [
        f"Se procesaron {len(routed)} noticias desde RSS y scraping; el macro router IA no produjo grupos validos.",
    ]

    return AiPhase2Report(
        status="ok",
        generated_at=datetime.now(UTC),
        regional_reports=regional_reports,
        global_summary=global_summary,
        editorial_cautions=[
            "Reporte intermedio ensamblado deterministicamente (macro router IA no disponible o fallo).",
        ],
    )


def _build_deterministic_topic_clusters(
    items: list[AiRoutedNewsInput],
    region: str,
    country: str | None,
) -> list[AiTopicCluster]:
    """Group items by topic and build deterministic AiTopicCluster objects."""
    by_topic: dict[str, list[AiRoutedNewsInput]] = defaultdict(list)
    for it in items:
        by_topic[it.topic].append(it)

    clusters: list[AiTopicCluster] = []
    for topic, topic_items in sorted(
        by_topic.items(),
        key=lambda kv: (max(n.impact_score for n in kv[1]) if kv[1] else 0),
        reverse=True,
    ):
        sorted_items = sorted(topic_items, key=lambda x: x.impact_score, reverse=True)
        observed_facts = [it.title for it in sorted_items[:5]]
        news_urls = [it.url for it in sorted_items]
        relevance = "high" if any(it.impact_score >= 8 for it in sorted_items) else "medium"

        clusters.append(AiTopicCluster(
            region=region,
            country=country,
            topic=topic,
            relevance=relevance,
            news_urls=news_urls,
            observed_facts=observed_facts,
            interpretation=[],
            affected_assets=[],
            watch_items=[],
            cautions=[],
        ))
    return clusters


def _build_deterministic_executive_summary(items: list[AiRoutedNewsInput]) -> list[str]:
    """Build a short executive summary from the top items by impact."""
    sorted_items = sorted(items, key=lambda x: x.impact_score, reverse=True)
    summary: list[str] = []
    for it in sorted_items[:4]:
        prefix = f"[{it.impact_score}] " if it.impact_score else ""
        summary.append(f"{prefix}{it.title}")
    return summary


def _build_deterministic_cautions(items: list[AiRoutedNewsInput], label: str) -> list[str]:
    """Build cautions for a deterministic regional report."""
    cautions: list[str] = []
    if not any(it.impact_score >= 7 for it in items):
        cautions.append(f"No se detectaron noticias de alto impacto para {label}.")
    if len(items) < 3:
        cautions.append(f"Cobertura limitada para {label} ({len(items)} noticias).")
    return cautions


def _build_fallback_report(macro_result: MacroRouterResult) -> AiPhase2Report:
    """Legacy minimal fallback when routed_news is also empty."""
    return AiPhase2Report(
        status="ok",
        generated_at=datetime.now(UTC),
        regional_reports=[],
        global_summary=[],
        editorial_cautions=[
            "Reporte intermedio generado como fallback: el macro router no produjo salida valida.",
        ],
    )


def _build_intermediate_report(
    macro_result: MacroRouterResult,
    topic_responses: list[tuple[str, str | None, AiTopicRouterResponse]],
    all_metadata: list[AiPhase2RunMetadata],
) -> AiPhase2Report | None:
    """Try IA consolidation first, fallback to deterministic assembly."""
    client = OllamaCloudClient()

    if not client.is_enabled():
        logger.info("Intermediate report: AI disabled, using deterministic assembly")
        return _deterministic_assembly(macro_result, topic_responses)

    macro_json = macro_result.response.model_dump(mode="json") if macro_result.response else {}
    micro_json = [
        {
            "region": region,
            "country": country,
            "clusters": [c.model_dump(mode="json") for c in resp.clusters],
        }
        for region, country, resp in topic_responses
    ]

    system_prompt = load_prompt("system_financial_editor")
    user_template = load_prompt("intermediate_report")
    user_prompt = (
        user_template
        .replace("{{MACRO_JSON}}", json.dumps(macro_json, ensure_ascii=False, indent=2))
        .replace("{{MICRO_JSON}}", json.dumps(micro_json, ensure_ascii=False, indent=2))
    )

    metadata = AiPhase2RunMetadata(
        model=client.settings.ollama_model,
        stage="intermediate_report",
        prompt_name="intermediate_report",
        input_news_count=macro_result.metadata.input_news_count,
        dry_run=client.is_dry_run(),
    )

    try:
        raw_text = client.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)
    except OllamaCloudError as e:
        metadata.validation_status = "skipped"
        metadata.error_message = str(e)
        all_metadata.append(metadata)
        logger.warning("Intermediate report IA failed, using deterministic: %s", e)
        return _deterministic_assembly(macro_result, topic_responses)

    try:
        report = validate_response(raw_text, AiPhase2Report, strict=client.settings.ai_strict_json)
        metadata.validation_status = "ok"
        all_metadata.append(metadata)
        return report
    except (JsonValidationError, ValidationError) as e:
        metadata.validation_status = "invalid_json" if isinstance(e, JsonValidationError) else "schema_error"
        metadata.error_message = str(e)
        all_metadata.append(metadata)
        logger.warning("Intermediate report validation failed, using deterministic: %s", e)
        return _deterministic_assembly(macro_result, topic_responses)


def _deterministic_assembly(
    macro_result: MacroRouterResult,
    topic_responses: list[tuple[str, str | None, AiTopicRouterResponse]],
) -> AiPhase2Report:
    """Assemble a report deterministically without IA, from macro + micro outputs."""
    regional_reports: list[AiIntermediateRegionalReport] = []

    topic_map: dict[tuple[str, str | None], AiTopicRouterResponse] = {
        (region, country): resp for region, country, resp in topic_responses
    }

    if macro_result.response:
        for group in macro_result.response.groups:
            key = (group.region, group.country)
            topic_resp = topic_map.get(key)
            clusters = topic_resp.clusters if topic_resp else []

            regional_reports.append(
                AiIntermediateRegionalReport(
                    region=group.region,
                    country=group.country,
                    executive_summary=group.key_facts[:3] if group.key_facts else [group.why_it_matters],
                    topic_clusters=clusters,
                    cross_asset_links=[],
                    watchlist=[],
                    cautions=group.cautions,
                )
            )

    global_summary: list[str] = []
    if macro_result.response:
        global_summary = macro_result.response.cautions[:3]

    return AiPhase2Report(
        status="ok",
        generated_at=datetime.now(UTC),
        regional_reports=regional_reports,
        global_summary=global_summary,
        editorial_cautions=["Reporte intermedio ensamblado deterministicamente."],
    )
