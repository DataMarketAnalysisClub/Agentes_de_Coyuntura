"""Editorial writer: converts a phase 2 report into an editorial email structure.

The writer is an IA agent (Ollama Cloud) that takes the AiPhase2Report plus
market snapshots and returns an AiEditorialEmail structure (subject, sections,
chart specs, cautions). If IA is disabled or fails, a deterministic fallback
is built from the phase 2 report.
"""

import json
import logging
from datetime import UTC, datetime

from pydantic import ValidationError

from app.config import Settings
from services.ai.chart_renderer import available_chart_ids
from services.ai.json_validation import JsonValidationError, validate_response
from services.ai.ollama_client import OllamaCloudClient, OllamaCloudError
from services.ai.prompt_loader import load_prompt
from services.ai.schemas import (
    AiEditorialEmail,
    AiEditorialRunMetadata,
    AiEditorialSection,
    AiPhase2Report,
)
from storage.models import MarketSnapshot

logger = logging.getLogger(__name__)


class EditorialWriterResult:
    def __init__(
        self,
        response: AiEditorialEmail | None,
        metadata: AiEditorialRunMetadata,
        fallback: AiEditorialEmail | None = None,
    ) -> None:
        self.response = response
        self.metadata = metadata
        self.fallback = fallback

    @property
    def ok(self) -> bool:
        return self.response is not None and self.metadata.validation_status == "ok"

    @property
    def email(self) -> AiEditorialEmail | None:
        return self.response or self.fallback


def run_editorial_writer(
    phase2_report: AiPhase2Report,
    snapshots: list[MarketSnapshot] | None = None,
    news: list | None = None,
    max_charts: int = 4,
    settings: Settings | None = None,
) -> EditorialWriterResult:
    """Run the editorial writer over a phase 2 report.

    `news` is accepted only to compute which chart ids are available; the writer
    itself consumes the phase 2 report, not the raw news.
    `max_charts` limits how many chart specs are kept (priority: change_pct,
    impact_ranking, assets_table, then region/topic distributions).
    """
    client = OllamaCloudClient(settings=settings)
    chart_ids = available_chart_ids(snapshots, news)
    limited_chart_ids = _prioritize_chart_ids(chart_ids, max_charts)

    metadata = AiEditorialRunMetadata(
        model=client.settings.ollama_model,
        input_regional_reports_count=len(phase2_report.regional_reports),
    )

    if not client.is_enabled():
        metadata.validation_status = "skipped"
        logger.info("Editorial writer skipped (AI_ENABLED=false)")
        return EditorialWriterResult(
            response=None,
            metadata=metadata,
            fallback=build_deterministic_editorial(phase2_report, snapshots, limited_chart_ids, news),
        )

    phase2_json = phase2_report.model_dump(mode="json")
    snapshots_payload = [
        {
            "symbol": s.symbol,
            "name": s.name,
            "price": s.price,
            "change_pct": s.change_pct,
            "source": s.source,
        }
        for s in (snapshots or [])
    ]

    exact_source_names = _collect_exact_source_names(news, snapshots)

    system_prompt = load_prompt("system_financial_editor")
    user_template = load_prompt("editorial_email_writer")
    user_prompt = (
        user_template
        .replace("{{PHASE2_JSON}}", json.dumps(phase2_json, ensure_ascii=False, indent=2))
        .replace("{{SNAPSHOTS_JSON}}", json.dumps(snapshots_payload, ensure_ascii=False, indent=2))
        .replace("{{AVAILABLE_CHART_IDS}}", ", ".join(limited_chart_ids) or "(ninguno)")
        .replace("{{EXACT_SOURCE_NAMES}}", ", ".join(exact_source_names) or "(ninguno)")
    )

    try:
        raw_text = client.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)
    except OllamaCloudError as e:
        metadata.validation_status = "skipped"
        metadata.error_message = str(e)
        logger.warning("Editorial writer skipped: %s", e)
        return EditorialWriterResult(
            response=None,
            metadata=metadata,
            fallback=build_deterministic_editorial(phase2_report, snapshots, limited_chart_ids, news),
        )

    try:
        response = validate_response(
            raw_text,
            AiEditorialEmail,
            strict=client.settings.ai_strict_json,
        )
        response = _filter_chart_specs(response, limited_chart_ids)
        response = _limit_chart_specs(response, max_charts)
        response.source_notes = _filter_source_notes(
            response.source_notes, exact_source_names,
        )
        metadata.validation_status = "ok"
        metadata.output_sections_count = len(response.sections)
        metadata.output_chart_specs_count = len(response.chart_specs)
        return EditorialWriterResult(response=response, metadata=metadata)
    except (JsonValidationError, ValidationError) as e:
        metadata.validation_status = "invalid_json" if isinstance(e, JsonValidationError) else "schema_error"
        metadata.error_message = str(e)
        logger.warning("Editorial writer validation failed, using fallback: %s", e)
        return EditorialWriterResult(
            response=None,
            metadata=metadata,
            fallback=build_deterministic_editorial(phase2_report, snapshots, limited_chart_ids, news),
        )


def _filter_chart_specs(email: AiEditorialEmail, valid_ids: list[str]) -> AiEditorialEmail:
    """Drop chart_specs and chart_ids references that are not in the valid catalog."""
    valid = set(valid_ids)
    email.chart_specs = [c for c in email.chart_specs if c.chart_id in valid]
    for section in email.sections:
        section.chart_ids = [cid for cid in section.chart_ids if cid in valid]
    return email


def _limit_chart_specs(email: AiEditorialEmail, max_charts: int) -> AiEditorialEmail:
    """Keep only the first max_charts chart_specs and update section chart_ids."""
    if max_charts <= 0:
        email.chart_specs = []
        for section in email.sections:
            section.chart_ids = []
        return email
    kept_ids = {spec.chart_id for spec in email.chart_specs[:max_charts]}
    email.chart_specs = email.chart_specs[:max_charts]
    for section in email.sections:
        section.chart_ids = [cid for cid in section.chart_ids if cid in kept_ids]
    return email


def _prioritize_chart_ids(chart_ids: list[str], max_charts: int) -> list[str]:
    """Order chart ids by editorial priority and limit to max_charts.

    Priority: impact_ranking_bar > assets_table > news_by_region_bar >
    news_by_topic_bar.
    """
    priority = [
        "impact_ranking_bar",
        "assets_table",
        "news_by_region_bar",
        "news_by_topic_bar",
    ]
    ordered = [cid for cid in priority if cid in chart_ids]
    ordered.extend([cid for cid in chart_ids if cid not in ordered])
    return ordered[:max_charts] if max_charts > 0 else []


def build_deterministic_editorial(
    phase2_report: AiPhase2Report,
    snapshots: list[MarketSnapshot] | None = None,
    available_ids: list[str] | None = None,
    news: list | None = None,
) -> AiEditorialEmail:
    """Build a deterministic editorial email when IA is unavailable or fails.

    The editorial uses the phase 2 report's regional_reports and topic_clusters
    to list concrete headlines from RSS/scraping, grouped by region and topic.
    Structure per region:
    - body: editorial paragraph separating facts from preliminary reading
    - bullets: unique observed facts (no duplicates)
    - cautions: editorial cautions
    """
    available_ids = available_ids or []
    sections: list[AiEditorialSection] = []

    for regional in phase2_report.regional_reports:
        label = regional.country or regional.region
        observed_facts: list[str] = []
        seen: set[str] = set()

        for fact in regional.executive_summary:
            clean = _strip_score_prefix(fact)
            if clean and clean not in seen:
                seen.add(clean)
                observed_facts.append(clean)

        topic_groups: list[tuple[str, list[str]]] = []
        for cluster in regional.topic_clusters:
            cluster_facts: list[str] = []
            for fact in cluster.observed_facts:
                clean = _strip_score_prefix(fact)
                if clean and clean not in seen:
                    seen.add(clean)
                    cluster_facts.append(clean)
            if cluster_facts:
                topic_groups.append((cluster.topic, cluster_facts))
            elif cluster.topic and not any(t == cluster.topic for t, _ in topic_groups):
                topic_groups.append((cluster.topic, []))

        if not observed_facts and not topic_groups:
            continue

        body = _build_editorial_paragraph(label, observed_facts, topic_groups, regional.cautions)

        bullets: list[str] = list(observed_facts)
        for topic, facts in topic_groups:
            if len(facts) >= 2:
                bullets.append(f"**En {topic.lower()}:** {facts[0]}")
                bullets.extend(facts[1:])
            elif len(facts) == 1:
                bullets.append(facts[0])

        sections.append(AiEditorialSection(
            heading=label,
            body=body,
            bullets=bullets,
            chart_ids=[],
            cautions=list(regional.cautions),
        ))

    if not sections and phase2_report.global_summary:
        sections.append(AiEditorialSection(
            heading="Resumen global",
            body=list(phase2_report.global_summary[:3]),
            bullets=[],
            chart_ids=[],
            cautions=[],
        ))

    market_context: list[str] = []
    for snap in (snapshots or [])[:5]:
        if snap.change_pct is not None:
            market_context.append(
                f"{snap.name or snap.symbol}: {snap.change_pct:+.2f}% (fuente: {snap.source})."
            )

    chart_specs = _deterministic_chart_specs(available_ids)
    chart_id_list = [spec.chart_id for spec in chart_specs]

    if chart_id_list:
        sections.append(AiEditorialSection(
            heading="Visualizaciones",
            body=["Graficos generados a partir de los datos disponibles."],
            bullets=[],
            chart_ids=chart_id_list,
            cautions=[],
        ))

    source_notes = _extract_source_notes(phase2_report, news)

    subject, headline, preheader = _build_subject_and_headline(
        phase2_report, sections, snapshots,
    )

    return AiEditorialEmail(
        status="ok",
        generated_at=datetime.now(UTC),
        subject=subject,
        preheader=preheader,
        headline=headline,
        executive_summary=list(phase2_report.global_summary) or _default_executive_summary(sections),
        market_context=market_context,
        sections=sections,
        risk_flags=[],
        chart_specs=chart_specs,
        source_notes=source_notes,
        editorial_cautions=list(phase2_report.editorial_cautions) + [
            "Email editorial ensamblado deterministicamente (IA no disponible).",
        ],
    )


def _strip_score_prefix(fact: str) -> str:
    """Strip leading [N] score prefix from a fact string."""
    import re
    return re.sub(r"^\[\d+\]\s*", "", fact).strip()


def _build_editorial_paragraph(
    label: str,
    observed_facts: list[str],
    topic_groups: list[tuple[str, list[str]]],
    cautions: list[str],
) -> list[str]:
    """Build a 2-paragraph editorial body: facts + preliminary reading."""
    if not observed_facts and not topic_groups:
        return []

    facts_para_parts: list[str] = []
    if observed_facts:
        facts_para_parts.append(
            f"En {label} se observaron {len(observed_facts)} hechos relevantes del dia."
        )
    elif topic_groups:
        topics_str = ", ".join(t for t, _ in topic_groups)
        facts_para_parts.append(
            f"En {label} el flujo se concentro en {topics_str}."
        )

    topics_for_para = [t for t, facts in topic_groups if facts]
    if topics_for_para:
        facts_para_parts.append(
            "Los topics principales son " + ", ".join(topics_for_para) + "."
        )

    facts_para = " ".join(facts_para_parts) if facts_para_parts else ""

    reading_parts: list[str] = []
    if observed_facts or topic_groups:
        reading_parts.append(_build_topic_reading(topic_groups))
    if cautions:
        reading_parts.append(" ".join(cautions))
    reading_para = " ".join(reading_parts) if reading_parts else ""

    body: list[str] = []
    if facts_para:
        body.append(facts_para)
    if reading_para:
        body.append(reading_para)
    return body


def _build_topic_reading(topic_groups: list[tuple[str, list[str]]]) -> str:
    """Build a topic-aware preliminary reading sentence.

    Replaces the generic v1 phrase with a reading that names the topics and
    their typical market implications. Each topic contributes a single clause;
    the final output is one sentence with a single "Lectura preliminar:" prefix.
    """
    if not topic_groups:
        return "Lectura preliminar: el flujo de noticias del dia no permite aislar un tema dominante."

    topic_clauses: dict[str, str] = {
        "bancos centrales": (
            "el foco en bancos centrales apunta a movimientos en expectativas de "
            "tasas, curva y dolar"
        ),
        "politica fiscal": (
            "el foco en politica fiscal sugiere tension sobre deuda soberana, "
            "credibilidad fiscal y tasas locales"
        ),
        "commodities": (
            "el foco en commodities suele trasladarse a cobre, China y terminos "
            "de intercambio"
        ),
        "forex": (
            "el foco en monedas globales puede presionar al CLP vial diferencial "
            "de tasas y dolar"
        ),
        "mercados": (
            "el foco en mercados refleja ajuste de apetito por riesgo y "
            "expectativas de tasas"
        ),
    }

    clauses: list[str] = []
    used: set[str] = set()
    for topic, _facts in topic_groups:
        key = topic.strip().lower()
        clause = topic_clauses.get(key)
        if clause and key not in used:
            clauses.append(clause)
            used.add(key)

    if not clauses:
        return "Lectura preliminar: el flujo del dia reune varios focos sin un tema dominante claro."

    if len(clauses) == 1:
        return f"Lectura preliminar: {clauses[0]}."

    head = "Lectura preliminar: " + clauses[0]
    tail = "; ".join(clauses[1:])
    return f"{head}; {tail}."


def _default_executive_summary(sections: list[AiEditorialSection]) -> list[str]:
    """Build a fallback executive summary from the first 2 regional sections.

    Prefers the last bullet of each section (less likely to be repeated as the
    first bullet of the section body). If a section has a single bullet, the
    summary skips that section to avoid duplicating content.
    """
    summary: list[str] = []
    for s in sections[:2]:
        if len(s.bullets) >= 2:
            summary.append(f"[{s.heading}] {s.bullets[-1]}")
    if not summary:
        summary.append("Resumen editorial automatico.")
    return summary


def _build_subject_and_headline(
    phase2_report: AiPhase2Report,
    sections: list[AiEditorialSection],
    snapshots: list[MarketSnapshot] | None,
) -> tuple[str, str, str]:
    """Build subject, headline, and preheader from top regions + topics + assets.

    Subject max 80 chars, preheader max 120 chars.
    """
    top_regions: list[str] = []
    for regional in phase2_report.regional_reports[:2]:
        label = regional.country or regional.region
        if label and label not in top_regions:
            top_regions.append(label)

    top_topics: list[str] = []
    for regional in phase2_report.regional_reports:
        for cluster in regional.topic_clusters:
            if cluster.topic and cluster.topic not in top_topics:
                top_topics.append(cluster.topic)
            if len(top_topics) >= 3:
                break
        if len(top_topics) >= 3:
            break

    mover_snap = None
    if snapshots:
        candidates = [s for s in snapshots if s.change_pct is not None]
        if candidates:
            mover_snap = max(candidates, key=lambda s: abs(s.change_pct or 0.0))

    subject_parts: list[str] = []
    if mover_snap and mover_snap.symbol == "COPPER":
        subject_parts.append("cobre")
    if top_regions:
        subject_parts.append(", ".join(top_regions))
    if subject_parts:
        subject = "DMAC Coyuntura: " + ", ".join(subject_parts)
    else:
        subject = "DMAC Coyuntura"
    if len(subject) > 80:
        subject = f"DMAC Coyuntura: {', '.join(top_regions[:2]) or 'mercados'}"

    mover_phrase = ""
    if mover_snap and mover_snap.symbol == "COPPER":
        mover_phrase = "cobre"

    regions_phrase = ", ".join(top_regions[:2])

    headline = _build_headline(mover_phrase, regions_phrase, top_topics)

    preheader_parts: list[str] = []
    if top_regions:
        preheader_parts.append(f"Foco en {', '.join(top_regions[:2])}")
    if top_topics:
        preheader_parts.append(f"topics: {', '.join(top_topics[:3])}")
    if mover_snap and mover_snap.change_pct is not None:
        preheader_parts.append(
            f"{mover_snap.name or mover_snap.symbol} {mover_snap.change_pct:+.2f}%"
        )
    preheader = ". ".join(preheader_parts)[:120]
    if not preheader:
        preheader = "Resumen automatico editorial (fallback deterministico)."

    return subject, headline, preheader


def _build_headline(
    mover_phrase: str,
    regions_phrase: str,
    top_topics: list[str],
) -> str:
    """Build a cleaner headline, avoiding the v1 'X, Y, y Z marcan la agenda' style.

    Priority:
    1. Mover + regions (e.g. 'Cobre y Chile marcan la jornada').
    2. Regions + topics (e.g. 'Chile: bancos centrales y politica fiscal').
    3. Regions only.
    4. Mover only.
    5. Generic fallback.
    """
    if mover_phrase and regions_phrase:
        return f"{mover_phrase.capitalize()} y {regions_phrase} marcan la jornada"

    if regions_phrase and top_topics:
        topics = ", ".join(top_topics[:2])
        return f"{regions_phrase}: foco en {topics}"

    if regions_phrase:
        return f"{regions_phrase} lidera la jornada"

    if mover_phrase:
        return f"{mover_phrase.capitalize()} lidera la jornada"

    return "Coyuntura regional y de mercados"


def _extract_source_notes(phase2_report: AiPhase2Report, news: list | None = None) -> list[str]:
    """Extract source names from news items if available, else from the report."""
    return _collect_exact_source_names(news, [])


def _collect_exact_source_names(news: list | None, snapshots: list | None) -> list[str]:
    """Collect the exact source names present in the input (news + snapshots)."""
    sources: set[str] = set()
    for n in news or []:
        source = getattr(n, "source", None)
        if source:
            sources.add(str(source))
    snap_source = None
    for s in snapshots or []:
        snap_source = getattr(s, "source", None)
        break
    if snap_source and snap_source not in sources:
        sources.add(str(snap_source))
    return sorted(sources)


def _filter_source_notes(
    source_notes: list[str],
    exact_source_names: list[str],
) -> list[str]:
    """Drop source_notes entries that are not in the exact source list.

    The IA sometimes invents aliases or domain names (e.g. "FT", "bcentral",
    "hacienda.cl"). This filter keeps only names that match the input sources
    (case-insensitive, substring-aware) so the reader-facing list stays
    truthful.
    """
    if not exact_source_names:
        return list(source_notes)
    exact_lower = [s.lower() for s in exact_source_names]
    out: list[str] = []
    for note in source_notes:
        note_l = note.lower()
        if any(
            note_l == el
            or note_l in el
            or el in note_l
            for el in exact_lower
        ):
            out.append(note)
    return out


def _deterministic_chart_specs(available_ids: list[str]) -> list:
    """Build chart specs deterministically for all available chart ids."""
    from services.ai.schemas import AiChartSpec

    specs_by_id = {
        "impact_ranking_bar": AiChartSpec(
            chart_id="impact_ranking_bar",
            chart_type="bar_impact_ranking",
            title="Noticias por impacto",
            subtitle="Top 10 por puntaje",
            source_label="Datos: fuentes internas DMAC",
        ),
        "news_by_region_bar": AiChartSpec(
            chart_id="news_by_region_bar",
            chart_type="bar_news_by_region",
            title="Noticias por region",
            subtitle="Distribucion regional",
            source_label="Datos: fuentes internas DMAC",
        ),
        "news_by_topic_bar": AiChartSpec(
            chart_id="news_by_topic_bar",
            chart_type="bar_news_by_topic",
            title="Noticias por topic",
            subtitle="Distribucion tematica",
            source_label="Datos: fuentes internas DMAC",
        ),
        "assets_table": AiChartSpec(
            chart_id="assets_table",
            chart_type="table_assets",
            title="Principales activos",
            subtitle="Precios y variaciones",
            source_label="Datos: yfinance",
        ),
    }
    return [specs_by_id[cid] for cid in available_ids if cid in specs_by_id]
