from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class AiNewsInput(BaseModel):
    """Single news item fed to the model. Mirrors NewsItem without persistence fields."""

    timestamp: datetime
    source: str
    title: str
    url: str
    summary: str = ""
    region: str = "Global"
    topic: str = "macro general"
    impact_score: int = 0


class AiMarketSnapshotInput(BaseModel):
    """Market snapshot fed to the model."""

    symbol: str
    name: str
    price: float | None = None
    change_pct: float | None = None
    source: str = "yfinance"


class AiSmokeTestResponse(BaseModel):
    """Minimal structured response for the phase 1 smoke test."""

    status: Literal["ok"]
    summary: str = Field(description="Resumen ejecutivo breve en espanol")
    high_impact_titles: list[str] = Field(
        default_factory=list,
        description="Titulares seleccionados como de alto impacto",
    )
    cautions: list[str] = Field(
        default_factory=list,
        description="Notas de cautela editorial",
    )


class AiHighImpactDecision(BaseModel):
    """Decision record for one news item being classified by the model."""

    title: str
    url: str
    source: str
    region: str
    topic: str
    impact_level: Literal["low", "medium", "high"]
    reason: str = Field(description="Justificacion breve en espanol")
    confidence: float = Field(ge=0.0, le=1.0)


class AiBriefDraft(BaseModel):
    """Draft brief produced by the model, to be rendered into HTML later."""

    subject: str
    executive_summary: list[str]
    facts: list[str] = Field(default_factory=list)
    interpretation: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    watchlist: list[str] = Field(default_factory=list)
    disclaimer: str = ""


class AiRunMetadata(BaseModel):
    """Metadata recorded for each AI call for audit purposes."""

    model: str
    provider: str = "ollama_cloud"
    prompt_name: str
    prompt_version: str = "1"
    duration_ms: int = 0
    input_news_count: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    dry_run: bool = False
    validation_status: Literal["ok", "invalid_json", "schema_error", "skipped"] = "ok"
    error_message: str = ""


class AiRoutedNewsInput(BaseModel):
    """News item enriched with country for routing."""

    id: str
    timestamp: datetime
    source: str
    title: str
    url: str
    summary: str = ""
    region: str = "Global"
    country: str | None = None
    topic: str = "macro general"
    impact_score: int = 0


class AiMacroRegionGroup(BaseModel):
    """A region/country group produced by the macro router."""

    region: str
    country: str | None = None
    relevance: Literal["low", "medium", "high"]
    main_topics: list[str] = Field(default_factory=list)
    news_urls: list[str] = Field(default_factory=list)
    key_facts: list[str] = Field(default_factory=list)
    why_it_matters: str = ""
    cautions: list[str] = Field(default_factory=list)


class AiMacroRouterResponse(BaseModel):
    """Structured response from the macro router."""

    status: Literal["ok"]
    groups: list[AiMacroRegionGroup] = Field(default_factory=list)
    discarded_urls: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)


class AiTopicCluster(BaseModel):
    """A topic cluster within a region/country produced by the micro router."""

    region: str
    country: str | None = None
    topic: str
    relevance: Literal["low", "medium", "high"]
    news_urls: list[str] = Field(default_factory=list)
    observed_facts: list[str] = Field(default_factory=list)
    interpretation: list[str] = Field(default_factory=list)
    affected_assets: list[str] = Field(default_factory=list)
    watch_items: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)


class AiTopicRouterResponse(BaseModel):
    """Structured response from the topic router."""

    status: Literal["ok"]
    clusters: list[AiTopicCluster] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)


class AiIntermediateRegionalReport(BaseModel):
    """Intermediate report for one region/country combining macro + micro."""

    region: str
    country: str | None = None
    executive_summary: list[str] = Field(default_factory=list)
    topic_clusters: list[AiTopicCluster] = Field(default_factory=list)
    cross_asset_links: list[str] = Field(default_factory=list)
    watchlist: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)


class AiPhase2Report(BaseModel):
    """Full phase 2 intermediate report."""

    status: Literal["ok"]
    generated_at: datetime
    report_type: Literal["phase2_intermediate"] = "phase2_intermediate"
    regional_reports: list[AiIntermediateRegionalReport] = Field(default_factory=list)
    global_summary: list[str] = Field(default_factory=list)
    editorial_cautions: list[str] = Field(default_factory=list)


class AiPhase2RunMetadata(BaseModel):
    """Metadata for a phase 2 stage call."""

    model: str
    provider: str = "ollama_cloud"
    stage: Literal["macro_router", "topic_router", "intermediate_report"]
    prompt_name: str
    prompt_version: str = "1"
    input_news_count: int = 0
    output_group_count: int = 0
    dry_run: bool = False
    validation_status: Literal["ok", "invalid_json", "schema_error", "skipped"] = "ok"
    error_message: str = ""


# --- Phase 3: Editorial email + charts ---


class AiChartSpec(BaseModel):
    """Spec for a deterministic chart, suggested by the IA or computed locally.

    The chart_id MUST exist in the available chart ids offered to the model.
    The chart_type tells the renderer how to build the chart from raw data.
    """

    chart_id: str
    chart_type: Literal[
        "bar_change_pct",
        "bar_impact_ranking",
        "bar_news_by_region",
        "bar_news_by_topic",
        "table_assets",
    ]
    title: str
    subtitle: str = ""
    source_label: str = "Datos: fuentes internas DMAC"

    @field_validator("subtitle", "source_label", "title", mode="before")
    @classmethod
    def _coerce_none_to_str(cls, value: object) -> object:
        if value is None:
            return ""
        return value


class AiEditorialSection(BaseModel):
    """A section of the editorial email, typically one per region/country."""

    heading: str
    body: list[str] = Field(default_factory=list)
    bullets: list[str] = Field(default_factory=list)
    chart_ids: list[str] = Field(default_factory=list)
    cautions: list[str] = Field(default_factory=list)


class AiEditorialEmail(BaseModel):
    """Full editorial email content produced by the IA writer."""

    status: Literal["ok"]
    generated_at: datetime
    subject: str
    preheader: str = ""
    headline: str = ""
    executive_summary: list[str] = Field(default_factory=list)
    market_context: list[str] = Field(default_factory=list)
    sections: list[AiEditorialSection] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    chart_specs: list[AiChartSpec] = Field(default_factory=list)
    source_notes: list[str] = Field(default_factory=list)
    editorial_cautions: list[str] = Field(default_factory=list)
    report_type: Literal["phase3_editorial_email"] = "phase3_editorial_email"


class AiEditorialRunMetadata(BaseModel):
    """Metadata for the phase 3 editorial writer call."""

    model: str
    provider: str = "ollama_cloud"
    stage: Literal["editorial_writer"] = "editorial_writer"
    prompt_name: str = "editorial_email_writer"
    prompt_version: str = "1"
    input_news_count: int = 0
    input_regional_reports_count: int = 0
    output_sections_count: int = 0
    output_chart_specs_count: int = 0
    dry_run: bool = False
    validation_status: Literal["ok", "invalid_json", "schema_error", "skipped"] = "ok"
    error_message: str = ""


class AiPhase3RunResult(BaseModel):
    """Bundle returned by the phase 3 pipeline for audit and rendering."""

    editorial: AiEditorialEmail
    chart_specs: list[AiChartSpec] = Field(default_factory=list)
    metadata: AiEditorialRunMetadata
    rendered_chart_ids: list[str] = Field(default_factory=list)
    fallback_used: bool = False
