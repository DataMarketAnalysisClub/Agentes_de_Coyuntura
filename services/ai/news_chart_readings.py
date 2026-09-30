"""Linea de lectura de Nix (IA) para cada grafico "En foco".

La seleccion de graficos sigue siendo deterministica (services/news_charts.py):
la IA solo redacta una linea por grafico ya elegido. Cualquier `symbol` que
la IA devuelva fuera de los candidatos se descarta, asi que nunca puede
agregar un activo que ninguna noticia menciona. Si la IA esta apagada, falla
o responde algo invalido, los graficos se muestran sin linea.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from dataclasses import replace

from pydantic import BaseModel, ValidationError

from app.config import Settings, get_settings
from services.ai.editorial_polish import polish_text
from services.ai.json_validation import JsonValidationError, validate_response
from services.ai.ollama_client import OllamaCloudClient, OllamaCloudError
from services.ai.prompt_loader import load_prompt
from services.news_charts import DEFAULT_MAX_NEWS_CHARTS, NewsChart, select_news_charts
from storage.models import MarketSnapshot, NewsItem

logger = logging.getLogger(__name__)

MAX_READING_CHARS = 220
MAX_HEADLINES_PER_CHART = 2
# Una lectura que sugiere operar se descarta: el correo no recomienda inversiones.
_ADVICE_RE = re.compile(r"\b(comprar|compre|vender|venda|mantener posicion|recomend\w*|oportunidad de compra)\b", re.I)


class ChartReading(BaseModel):
    symbol: str
    reading: str


class ChartReadingsResponse(BaseModel):
    readings: list[ChartReading] = []


def select_news_charts_with_readings(
    news: Iterable[NewsItem],
    snapshots: Iterable[MarketSnapshot],
    settings: Settings | None = None,
    max_charts: int = DEFAULT_MAX_NEWS_CHARTS,
    client: OllamaCloudClient | None = None,
) -> list[NewsChart]:
    """Graficos "En foco" deterministicos, con la lectura de Nix si la IA esta activa."""
    current = settings or get_settings()
    charts = select_news_charts(news, snapshots, max_charts=max_charts)
    if not charts or not (current.ai_enabled and current.ai_brief_enabled):
        return charts
    try:
        readings = generate_chart_readings(charts, client or OllamaCloudClient(current))
    except Exception:
        # La lectura es opcional: un error inesperado no debe frenar el correo.
        logger.warning("News chart readings failed", exc_info=True)
        return charts
    return [replace(chart, reading=readings.get(chart.snapshot.symbol, "")) for chart in charts]


def generate_chart_readings(charts: list[NewsChart], client: OllamaCloudClient) -> dict[str, str]:
    """Pide a la IA una linea por grafico y devuelve solo las validas, por simbolo."""
    if not charts:
        return {}
    user_prompt = load_prompt("news_chart_reading").replace(
        "{{CHARTS_JSON}}", json.dumps(_charts_payload(charts), ensure_ascii=False, indent=2)
    )
    try:
        raw_text = client.chat_json(system_prompt=load_prompt("system_financial_editor"), user_prompt=user_prompt)
        response = validate_response(raw_text, ChartReadingsResponse, strict=client.settings.ai_strict_json)
    except (OllamaCloudError, JsonValidationError, ValidationError) as exc:
        logger.warning("News chart readings skipped", extra={"error_type": type(exc).__name__, "error": str(exc)})
        return {}
    return _valid_readings(response, {chart.snapshot.symbol for chart in charts})


def _charts_payload(charts: list[NewsChart]) -> list[dict[str, object]]:
    return [
        {
            "symbol": chart.snapshot.symbol,
            "asset": chart.snapshot.name,
            "day_change_pct": chart.snapshot.change_pct,
            "period_change_pct": None if chart.period_change_pct is None else round(chart.period_change_pct, 2),
            "period_points": len(chart.snapshot.history),
            "headlines": [
                {"title": item.title, "source": item.source} for item in chart.news[:MAX_HEADLINES_PER_CHART]
            ],
        }
        for chart in charts
    ]


def _valid_readings(response: ChartReadingsResponse, candidates: set[str]) -> dict[str, str]:
    readings: dict[str, str] = {}
    for item in response.readings:
        symbol = item.symbol.strip().upper()
        text = polish_text(re.sub(r"\s+", " ", item.reading).strip())
        if symbol not in candidates:
            logger.warning("Discarding chart reading for non-candidate asset", extra={"symbol": symbol})
            continue
        if not text or symbol in readings or len(text) > MAX_READING_CHARS or _ADVICE_RE.search(text):
            continue
        readings[symbol] = text
    return readings
