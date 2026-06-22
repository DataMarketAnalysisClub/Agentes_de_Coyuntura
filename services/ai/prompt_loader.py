import logging
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parents[2] / "prompts" / "ai"


class PromptNotFoundError(FileNotFoundError):
    pass


@lru_cache(maxsize=32)
def load_prompt(name: str) -> str:
    """Load a markdown prompt from prompts/ai/ by name (without extension).

    Raises PromptNotFoundError if the file is missing.
    """
    path = PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise PromptNotFoundError(f"Prompt not found: {path}")
    return path.read_text(encoding="utf-8")


def list_available_prompts() -> list[str]:
    """Return the names (without extension) of available prompts."""
    if not PROMPTS_DIR.exists():
        return []
    return sorted(p.stem for p in PROMPTS_DIR.glob("*.md"))
