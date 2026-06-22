import json
import logging
import time
from typing import Any

from app.config import Settings, get_settings
from app.http_client import ResilientHttpClient

logger = logging.getLogger(__name__)


class OllamaCloudError(Exception):
    pass


class OllamaCloudClient:
    """Client for Ollama Cloud chat completions API.

    Supports dry-run mode and structured (JSON) outputs.
    Does NOT collect data, scrape, or make business decisions.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._http: ResilientHttpClient | None = None

    @property
    def http_client(self) -> ResilientHttpClient:
        if self._http is None:
            self._http = ResilientHttpClient(
                name="ollama_cloud",
                timeout=self.settings.ollama_timeout_seconds,
                retries=self.settings.ollama_max_retries,
            )
        return self._http

    def is_enabled(self) -> bool:
        return self.settings.ai_enabled

    def is_dry_run(self) -> bool:
        return self.settings.ai_dry_run

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str | None = None,
        temperature: float | None = None,
    ) -> str:
        """Send a chat request and return the raw model text.

        In dry-run mode, returns a deterministic stub JSON string
        without hitting the network.
        """
        if not self.is_enabled():
            logger.info("AI disabled, skipping Ollama Cloud call")
            raise OllamaCloudError("AI is disabled (AI_ENABLED=false)")

        selected_model = model or self.settings.ollama_model
        selected_temp = temperature if temperature is not None else self.settings.ollama_temperature

        if not selected_model:
            raise OllamaCloudError("No Ollama model configured (OLLAMA_MODEL empty)")

        if self.is_dry_run():
            logger.info(
                "AI dry-run: returning stub response",
                extra={"model": selected_model, "prompt_chars": len(user_prompt)},
            )
            return self._dry_run_stub()

        if not self.settings.ollama_api_key:
            raise OllamaCloudError("Missing OLLAMA_API_KEY")

        return self._call_api(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            model=selected_model,
            temperature=selected_temp,
        )

    def _call_api(
        self,
        system_prompt: str,
        user_prompt: str,
        model: str,
        temperature: float,
    ) -> str:
        url = f"{self.settings.ollama_base_url.rstrip('/')}/api/chat"
        headers = {
            "Authorization": f"Bearer {self.settings.ollama_api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": model,
            "stream": False,
            "format": "json",
            "options": {"temperature": temperature},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }

        start = time.monotonic()
        try:
            response = self.http_client.post(url, headers=headers, json=body)
            response.raise_for_status()
        except Exception as e:
            logger.warning("Ollama Cloud request failed", extra={"error": str(e)})
            raise OllamaCloudError(f"Ollama Cloud request failed: {e}") from e

        duration_ms = int((time.monotonic() - start) * 1000)
        data: dict[str, Any] = response.json()
        content = data.get("message", {}).get("content", "")
        logger.info(
            "Ollama Cloud call completed",
            extra={
                "model": model,
                "duration_ms": duration_ms,
                "content_chars": len(content),
            },
        )
        return content

    @staticmethod
    def _dry_run_stub() -> str:
        return json.dumps(
            {
                "status": "ok",
                "summary": "Dry-run stub: IA no ejecutada. Revisa AI_DRY_RUN y AI_ENABLED.",
                "high_impact_titles": [],
                "cautions": ["Respuesta generada en modo dry-run."],
            },
            ensure_ascii=False,
        )
