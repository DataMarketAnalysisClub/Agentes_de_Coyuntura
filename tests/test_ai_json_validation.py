import pytest
from pydantic import BaseModel

from services.ai.json_validation import JsonValidationError, extract_json, validate_response


class _Stub(BaseModel):
    status: str
    value: int


class TestJsonValidation:
    def test_extract_json_strict_valid(self) -> None:
        result = extract_json('{"status": "ok", "value": 1}', strict=True)
        assert result == {"status": "ok", "value": 1}

    def test_extract_json_strict_rejects_extra_text(self) -> None:
        with pytest.raises(JsonValidationError):
            extract_json('Here is the JSON: {"status": "ok"}', strict=True)

    def test_extract_json_non_strict_finds_block(self) -> None:
        text = 'Some preamble\n{"status": "ok", "value": 2}\ntrailer'
        result = extract_json(text, strict=False)
        assert result == {"status": "ok", "value": 2}

    def test_extract_json_non_strict_no_block_raises(self) -> None:
        with pytest.raises(JsonValidationError):
            extract_json("no json here", strict=False)

    def test_validate_response_ok(self) -> None:
        text = '{"status": "ok", "value": 5}'
        result = validate_response(text, _Stub, strict=True)
        assert isinstance(result, _Stub)
        assert result.value == 5

    def test_validate_response_schema_error(self) -> None:
        text = '{"status": "ok"}'
        with pytest.raises(Exception):
            validate_response(text, _Stub, strict=True)

    def test_validate_response_invalid_json(self) -> None:
        with pytest.raises(JsonValidationError):
            validate_response("not json", _Stub, strict=True)
