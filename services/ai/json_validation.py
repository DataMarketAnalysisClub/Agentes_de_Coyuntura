import json
import logging
import re
from typing import Any

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)


class JsonValidationError(Exception):
    pass


def extract_json(text: str, strict: bool = True) -> Any:
    """Extract a JSON object from a model response.

    If strict=True, the whole text must be valid JSON (after stripping).
    If strict=False, attempt to find the first {...} or [...] block.
    """
    stripped = text.strip()
    if strict:
        try:
            return json.loads(stripped)
        except json.JSONDecodeError as e:
            raise JsonValidationError(f"Strict JSON parse failed: {e}") from e

    # Try direct parse first.
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass

    # Fallback: find first balanced object/array block.
    match = re.search(r"\{.*\}|\[.*\]", stripped, re.DOTALL)
    if not match:
        raise JsonValidationError("No JSON block found in text")
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError as e:
        raise JsonValidationError(f"JSON block parse failed: {e}") from e


def validate_response(
    text: str,
    model: type[BaseModel],
    strict: bool = True,
) -> BaseModel:
    """Extract JSON from text and validate against a Pydantic model.

    Raises JsonValidationError on parse errors, or re-raises ValidationError.
    """
    payload = extract_json(text, strict=strict)
    try:
        return model.model_validate(payload)
    except ValidationError as e:
        logger.warning("Schema validation failed", extra={"error": str(e)})
        raise
