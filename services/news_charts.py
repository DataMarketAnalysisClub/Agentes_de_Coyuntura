"""Graficos guiados por noticias ("En foco").

Concepto: los graficos del correo no son un catalogo fijo, sino que se
seleccionan segun las noticias que el correo publica. Si un titular habla de
cobre y del peso chileno, la seccion muestra la serie de 1 mes del Cobre y del
USD/CLP, y cada grafico cita el titular que lo activo.

La seleccion es deterministica y auditable (palabras clave con limites de
palabra, sin IA): cada grafico se puede explicar por un titular concreto.
Solo se grafican activos con historia de precios suficiente (yfinance).
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from services.news_classifier import normalize_text
from storage.models import MarketSnapshot, NewsItem

logger = logging.getLogger(__name__)

DEFAULT_MAX_NEWS_CHARTS = 3
MIN_HISTORY_POINTS = 5
# Una mencion en el titular pesa mas que una en el resumen.
TITLE_WEIGHT = 2.0
SUMMARY_WEIGHT = 1.0
# Los primeros titulares del correo son los mas relevantes.
POSITION_DECAY = 0.85

# Palabras clave por activo, ya normalizadas (minusculas, sin tildes). Se
# buscan como palabras completas: "oil" no calza con "turmoil" ni "oro" con
# "tesoro". Solo terminos que nombran al activo; nada generico como
# "mercados" o "commodities", que activarian graficos sin relacion real.
ASSET_NEWS_KEYWORDS: dict[str, tuple[str, ...]] = {
    "USDCLP": ("dolar", "peso chileno", "tipo de cambio", "usd/clp", "usdclp", "clp"),
    # Minas de cobre chilenas: una huelga en Escondida mueve el precio del cobre.
    "COPPER": (
        "cobre", "copper", "codelco", "cochilco", "escondida", "centinela",
        "chuquicamata", "el teniente", "collahuasi", "los pelambres",
    ),
    "IPSA": ("ipsa", "bolsa de santiago", "bolsa chilena", "acciones chilenas"),
    "SP500": ("s&p 500", "s&p500", "sp500", "wall street", "wall st", "u.s. stocks", "us stocks"),
    "NASDAQ100": ("nasdaq",),
    # "bonds"/"yields" solo en ingles (fuentes globales/EE.UU.); "bonos" en
    # castellano suele ser deuda local (ej. bonos soberanos de Chile).
    "US10Y": (
        "treasury", "treasuries", "bonos del tesoro", "10-year yield", "rendimiento del bono",
        "yields", "bond yields", "bond", "bonds",
    ),
    # "dollar" (ingles) -> indice DXY; "dolar" (castellano, prensa chilena) -> USD/CLP.
    "DXY": ("dxy", "dollar index", "indice dolar", "indice del dolar", "greenback", "dollar"),
    "GOLD": ("oro", "gold"),
    "WTI": ("wti", "west texas"),
    # Referencia internacional: "petroleo"/"oil" sin especificar va a Brent.
    "BRENT": ("brent", "petroleo", "crudo", "oil", "crude", "opep", "opec"),
    "EUROSTOXX50": ("euro stoxx", "eurostoxx", "bolsas europeas", "european stocks", "european shares"),
    "BOVESPA": ("bovespa", "ibovespa", "bolsa de sao paulo"),
    "MEXIPC": ("bolsa mexicana", "bmv"),
    "USDBRL": ("real brasileno", "brazilian real"),
    "USDMXN": ("peso mexicano", "mexican peso"),
    "USDCOP": ("peso colombiano", "colombian peso"),
    "USDPEN": ("sol peruano", "peruvian sol"),
}


def _compile(keywords: tuple[str, ...]) -> re.Pattern[str]:
    alternatives = "|".join(re.escape(keyword) for keyword in keywords)
    # \b no sirve en bordes con simbolos ("s&p 500", "usd/clp"): se exige que
    # no haya letra ni digito pegado a cada lado.
    return re.compile(rf"(?<![a-z0-9])(?:{alternatives})(?![a-z0-9])")


_ASSET_PATTERNS: dict[str, re.Pattern[str]] = {
    symbol: _compile(keywords) for symbol, keywords in ASSET_NEWS_KEYWORDS.items()
}


@dataclass(frozen=True)
class NewsChart:
    """Un grafico seleccionado por noticias, listo para renderizar."""

    snapshot: MarketSnapshot
    news: tuple[NewsItem, ...]
    score: float = field(compare=False)
    # Linea de lectura de Nix (IA), opcional: ver services/ai/news_chart_readings.py.
    reading: str = field(default="", compare=False)

    @property
    def period_change_pct(self) -> float | None:
        history = self.snapshot.history
        if len(history) < 2 or not history[0]:
            return None
        return (history[-1] / history[0] - 1) * 100


def assets_mentioned(item: NewsItem) -> dict[str, float]:
    """Activos que menciona una noticia y el peso de la mencion."""
    title = normalize_text(item.title)
    summary = normalize_text(item.summary or "")
    mentions: dict[str, float] = {}
    for symbol, pattern in _ASSET_PATTERNS.items():
        if pattern.search(title):
            mentions[symbol] = TITLE_WEIGHT
        elif pattern.search(summary):
            mentions[symbol] = SUMMARY_WEIGHT
    return mentions


def select_news_charts(
    news: Iterable[NewsItem],
    snapshots: Iterable[MarketSnapshot],
    max_charts: int = DEFAULT_MAX_NEWS_CHARTS,
) -> list[NewsChart]:
    """Elige los activos a graficar segun las noticias publicadas.

    Puntaje por activo = suma, por cada noticia que lo menciona, de
    peso_mencion x (1 + impacto/10) x decaimiento por posicion. Empates se
    resuelven por el movimiento del dia mas grande. Si ninguna noticia
    menciona un activo con historia, no hay graficos (la seccion no aparece).
    """
    if max_charts <= 0:
        return []

    chartable = {
        snapshot.symbol: snapshot
        for snapshot in snapshots
        if len(snapshot.history) >= MIN_HISTORY_POINTS and snapshot.price is not None
    }
    if not chartable:
        return []

    scores: dict[str, float] = {}
    related: dict[str, list[NewsItem]] = {}
    for position, item in enumerate(news):
        position_weight = POSITION_DECAY**position
        impact_weight = 1 + max(0, min(item.impact_score, 10)) / 10
        for symbol, mention_weight in assets_mentioned(item).items():
            if symbol not in chartable:
                continue
            scores[symbol] = scores.get(symbol, 0.0) + mention_weight * impact_weight * position_weight
            related.setdefault(symbol, []).append(item)

    ranked = sorted(
        scores,
        key=lambda symbol: (scores[symbol], abs(chartable[symbol].change_pct or 0.0)),
        reverse=True,
    )
    charts = [
        NewsChart(snapshot=chartable[symbol], news=tuple(related[symbol]), score=round(scores[symbol], 3))
        for symbol in ranked[:max_charts]
    ]
    logger.info(
        "News-driven charts selected",
        extra={"charts": [(chart.snapshot.symbol, chart.score) for chart in charts]},
    )
    return charts
