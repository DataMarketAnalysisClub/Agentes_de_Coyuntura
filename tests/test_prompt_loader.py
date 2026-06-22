import pytest

from services.ai.prompt_loader import PromptNotFoundError, list_available_prompts, load_prompt


class TestPromptLoader:
    def test_load_prompt_system_financial_editor(self) -> None:
        content = load_prompt("system_financial_editor")
        assert "editor" in content.lower() or "analista" in content.lower()
        assert len(content) > 50

    def test_load_prompt_json_smoke_test(self) -> None:
        content = load_prompt("json_smoke_test")
        assert "{{NEWS_JSON}}" in content
        assert "{{SNAPSHOTS_JSON}}" in content

    def test_load_prompt_missing_raises(self) -> None:
        with pytest.raises(PromptNotFoundError):
            load_prompt("does_not_exist")

    def test_list_available_prompts_includes_known(self) -> None:
        names = list_available_prompts()
        assert "system_financial_editor" in names
        assert "json_smoke_test" in names

    def test_load_prompt_is_cached(self) -> None:
        first = load_prompt("json_smoke_test")
        second = load_prompt("json_smoke_test")
        assert first is second

    def test_load_prompt_macro_region_router(self) -> None:
        content = load_prompt("macro_region_router")
        assert "{{NEWS_JSON}}" in content
        assert "{{SNAPSHOTS_JSON}}" in content

    def test_load_prompt_topic_micro_router(self) -> None:
        content = load_prompt("topic_micro_router")
        assert "{{NEWS_JSON}}" in content
        assert "{{REGION_LABEL}}" in content

    def test_load_prompt_intermediate_report(self) -> None:
        content = load_prompt("intermediate_report")
        assert "{{MACRO_JSON}}" in content
        assert "{{MICRO_JSON}}" in content

    def test_load_prompt_editorial_email_writer(self) -> None:
        content = load_prompt("editorial_email_writer")
        assert "{{PHASE2_JSON}}" in content
        assert "{{SNAPSHOTS_JSON}}" in content
        assert "{{AVAILABLE_CHART_IDS}}" in content
