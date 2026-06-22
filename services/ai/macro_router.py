"""Macro router: groups news by region/country using Ollama Cloud."""

import json
import logging

from pydantic import ValidationError

from app.config import Settings
from services.ai.grouping import select_and_prepare
from services.ai.json_validation import JsonValidationError, validate_response
from services.ai.ollama_client import OllamaCloudClient, OllamaCloudError
from services.ai.prompt_loader import load_prompt
from services.ai.schemas import (
    AiMacroRouterResponse,
    AiMarketSnapshotInput,
    AiPhase2RunMetadata,
    AiRoutedNewsInput,
)
from storage.models import MarketSnapshot, NewsItem

logger = logging.getLogger(__name__)


class MacroRouterResult:
    def __init__(
        self,
        response: AiMacroRouterResponse | None,
        metadata: AiPhase2RunMetadata,
        routed_news: list[AiRoutedNewsInput],
    ) -> None:
        self.response = response
        self.metadata = metadata
        self.routed_news = routed_news

    @property
    def ok(self) -> bool:
        return self.response is not None and self.metadata.validation_status == "ok"


def run_macro_router(
    news_items: list[NewsItem],
    snapshots: list[MarketSnapshot] | None = None,
    max_news: int = 30,
    settings: Settings | None = None,
) -> MacroRouterResult:
    """Run the macro router over already-collected news."""
    client = OllamaCloudClient(settings=settings)

    routed_news = select_and_prepare(news_items, max_news=max_news)
    news_payload = [item.model_dump(mode="json") for item in routed_news]
    snapshots_payload = [
        AiMarketSnapshotInput(
            symbol=s.symbol,
            name=s.name,
            price=s.price,
            change_pct=s.change_pct,
            source=s.source,
        ).model_dump(mode="json")
        for s in (snapshots or [])
    ]

    metadata = AiPhase2RunMetadata(
        model=client.settings.ollama_model,
        stage="macro_router",
        prompt_name="macro_region_router",
        input_news_count=len(routed_news),
        dry_run=client.is_dry_run(),
    )

    if not client.is_enabled():
        metadata.validation_status = "skipped"
        logger.info("Macro router skipped (AI_ENABLED=false)")
        return MacroRouterResult(response=None, metadata=metadata, routed_news=routed_news)

    system_prompt = load_prompt("system_financial_editor")
    user_template = load_prompt("macro_region_router")
    user_prompt = (
        user_template
        .replace("{{NEWS_JSON}}", json.dumps(news_payload, ensure_ascii=False, indent=2))
        .replace("{{SNAPSHOTS_JSON}}", json.dumps(snapshots_payload, ensure_ascii=False, indent=2))
    )

    try:
        raw_text = client.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)
    except OllamaCloudError as e:
        metadata.validation_status = "skipped"
        metadata.error_message = str(e)
        logger.warning("Macro router skipped: %s", e)
        return MacroRouterResult(response=None, metadata=metadata, routed_news=routed_news)

    try:
        response = validate_response(
            raw_text,
            AiMacroRouterResponse,
            strict=client.settings.ai_strict_json,
        )
        metadata.validation_status = "ok"
        metadata.output_group_count = len(response.groups)
        return MacroRouterResult(response=response, metadata=metadata, routed_news=routed_news)
    except (JsonValidationError, ValidationError) as e:
        metadata.validation_status = "invalid_json" if isinstance(e, JsonValidationError) else "schema_error"
        metadata.error_message = str(e)
        logger.warning("Macro router validation failed: %s", e)
        return MacroRouterResult(response=None, metadata=metadata, routed_news=routed_news)


def news_for_group(
    routed_news: list[AiRoutedNewsInput],
    group_urls: list[str],
) -> list[AiRoutedNewsInput]:
    """Filter routed news to only those in a macro group's URLs."""
    url_set = set(group_urls)
    return [item for item in routed_news if item.url in url_set]
