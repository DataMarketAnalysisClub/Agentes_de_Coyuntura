"""Topic router: groups news by topic within a region using Ollama Cloud."""

import json
import logging

from pydantic import ValidationError

from app.config import Settings
from services.ai.json_validation import JsonValidationError, validate_response
from services.ai.ollama_client import OllamaCloudClient, OllamaCloudError
from services.ai.prompt_loader import load_prompt
from services.ai.schemas import (
    AiMarketSnapshotInput,
    AiPhase2RunMetadata,
    AiRoutedNewsInput,
    AiTopicRouterResponse,
)
from storage.models import MarketSnapshot

logger = logging.getLogger(__name__)


class TopicRouterResult:
    def __init__(
        self,
        response: AiTopicRouterResponse | None,
        metadata: AiPhase2RunMetadata,
    ) -> None:
        self.response = response
        self.metadata = metadata

    @property
    def ok(self) -> bool:
        return self.response is not None and self.metadata.validation_status == "ok"


def run_topic_router(
    region_news: list[AiRoutedNewsInput],
    snapshots: list[MarketSnapshot] | None,
    region_label: str,
    max_per_group: int = 10,
    settings: Settings | None = None,
) -> TopicRouterResult:
    """Run the topic micro router for a single region/country."""
    client = OllamaCloudClient(settings=settings)

    from services.ai.grouping import limit_groups

    limited = limit_groups(region_news, max_per_group=max_per_group)
    news_payload = [item.model_dump(mode="json") for item in limited]
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
        stage="topic_router",
        prompt_name="topic_micro_router",
        input_news_count=len(limited),
        dry_run=client.is_dry_run(),
    )

    if not client.is_enabled():
        metadata.validation_status = "skipped"
        logger.info("Topic router skipped for %s (AI_ENABLED=false)", region_label)
        return TopicRouterResult(response=None, metadata=metadata)

    system_prompt = load_prompt("system_financial_editor")
    user_template = load_prompt("topic_micro_router")
    user_prompt = (
        user_template
        .replace("{{NEWS_JSON}}", json.dumps(news_payload, ensure_ascii=False, indent=2))
        .replace("{{SNAPSHOTS_JSON}}", json.dumps(snapshots_payload, ensure_ascii=False, indent=2))
        .replace("{{REGION_LABEL}}", region_label)
    )

    try:
        raw_text = client.chat_json(system_prompt=system_prompt, user_prompt=user_prompt)
    except OllamaCloudError as e:
        metadata.validation_status = "skipped"
        metadata.error_message = str(e)
        logger.warning("Topic router skipped for %s: %s", region_label, e)
        return TopicRouterResult(response=None, metadata=metadata)

    try:
        response = validate_response(
            raw_text,
            AiTopicRouterResponse,
            strict=client.settings.ai_strict_json,
        )
        metadata.validation_status = "ok"
        metadata.output_group_count = len(response.clusters)
        return TopicRouterResult(response=response, metadata=metadata)
    except (JsonValidationError, ValidationError) as e:
        metadata.validation_status = "invalid_json" if isinstance(e, JsonValidationError) else "schema_error"
        metadata.error_message = str(e)
        logger.warning("Topic router validation failed for %s: %s", region_label, e)
        return TopicRouterResult(response=None, metadata=metadata)
