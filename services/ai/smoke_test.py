import json
import logging

from pydantic import ValidationError

from services.ai.json_validation import JsonValidationError, validate_response
from services.ai.ollama_client import OllamaCloudClient, OllamaCloudError
from services.ai.prompt_loader import load_prompt
from services.ai.schemas import (
    AiMarketSnapshotInput,
    AiNewsInput,
    AiRunMetadata,
    AiSmokeTestResponse,
)
from storage.models import MarketSnapshot, NewsItem

logger = logging.getLogger(__name__)

MAX_NEWS_DEFAULT = 30


class SmokeTestResult:
    """Result of a smoke test run, including metadata and the parsed response."""

    def __init__(
        self,
        response: AiSmokeTestResponse | None,
        metadata: AiRunMetadata,
    ) -> None:
        self.response = response
        self.metadata = metadata

    @property
    def ok(self) -> bool:
        return self.response is not None and self.metadata.validation_status == "ok"


def run_smoke_test(
    news_items: list[NewsItem],
    snapshots: list[MarketSnapshot] | None = None,
    max_news: int = MAX_NEWS_DEFAULT,
) -> SmokeTestResult:
    """Run the phase 1 AI smoke test over already-collected news.

    Does NOT collect data. Consumes NewsItem and MarketSnapshot that were
    already produced by the deterministic pipeline.
    """
    client = OllamaCloudClient()

    selected_news = sorted(
        news_items,
        key=lambda n: n.impact_score or 0,
        reverse=True,
    )[:max_news]

    news_payload = [_news_to_input(n).model_dump(mode="json") for n in selected_news]
    snapshots_payload = (
        [_snapshot_to_input(s).model_dump(mode="json") for s in (snapshots or [])]
        if snapshots
        else []
    )

    system_prompt = load_prompt("system_financial_editor")
    user_template = load_prompt("json_smoke_test")

    user_prompt = user_template.replace(
        "{{NEWS_JSON}}",
        json.dumps(news_payload, ensure_ascii=False, indent=2),
    ).replace(
        "{{SNAPSHOTS_JSON}}",
        json.dumps(snapshots_payload, ensure_ascii=False, indent=2),
    )

    metadata = AiRunMetadata(
        model=client.settings.ollama_model,
        provider="ollama_cloud",
        prompt_name="json_smoke_test",
        input_news_count=len(selected_news),
        dry_run=client.is_dry_run(),
    )

    if not client.is_enabled():
        metadata.validation_status = "skipped"
        logger.info("Smoke test skipped (AI_ENABLED=false)")
        return SmokeTestResult(response=None, metadata=metadata)

    try:
        raw_text = client.chat_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
    except OllamaCloudError as e:
        metadata.validation_status = "skipped"
        metadata.error_message = str(e)
        logger.warning("Smoke test skipped: %s", e)
        return SmokeTestResult(response=None, metadata=metadata)

    try:
        response = validate_response(
            raw_text,
            AiSmokeTestResponse,
            strict=client.settings.ai_strict_json,
        )
        metadata.validation_status = "ok"
        return SmokeTestResult(response=response, metadata=metadata)
    except JsonValidationError as e:
        metadata.validation_status = "invalid_json"
        metadata.error_message = str(e)
        logger.warning("Smoke test JSON validation failed: %s", e)
        return SmokeTestResult(response=None, metadata=metadata)
    except ValidationError as e:
        metadata.validation_status = "schema_error"
        metadata.error_message = str(e)
        logger.warning("Smoke test schema validation failed: %s", e)
        return SmokeTestResult(response=None, metadata=metadata)


def _news_to_input(item: NewsItem) -> AiNewsInput:
    return AiNewsInput(
        timestamp=item.timestamp,
        source=item.source,
        title=item.title,
        url=item.url,
        summary=item.summary or "",
        region=item.region,
        topic=item.topic,
        impact_score=item.impact_score or 0,
    )


def _snapshot_to_input(snap: MarketSnapshot) -> AiMarketSnapshotInput:
    return AiMarketSnapshotInput(
        symbol=snap.symbol,
        name=snap.name,
        price=snap.price,
        change_pct=snap.change_pct,
        source=snap.source,
    )
