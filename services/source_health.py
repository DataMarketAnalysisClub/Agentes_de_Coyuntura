"""Salud de fuentes: detecta degradaciones silenciosas.

Las fuentes que fallan no lanzan excepcion hasta el job (registran un warning
y devuelven [] o None), asi que un feed vacio, un ticker que Yahoo dejo de
publicar o una serie vencida no se notaban en el correo. Este modulo evalua
cada corrida a partir de lo que llego versus lo que se esperaba.

Solo funciones puras: la persistencia y los avisos viven en
services/source_health_report.py.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from data_sources.rss_news_client import RawNewsItem
from storage.models import MarketSnapshot


class HealthStatus(StrEnum):
    OK = "ok"
    DEGRADED = "degradada"
    DOWN = "caida"


class SourceKind(StrEnum):
    NEWS = "noticias"
    MARKET = "mercado"
    MACRO = "macro"


# Frescura maxima de la nota mas reciente de cada feed. La Fed y el BCE
# publican pocos comunicados y no los fines de semana.
DEFAULT_NEWS_FRESHNESS_HOURS = 48
NEWS_FRESHNESS_HOURS: dict[str, int] = {"Federal Reserve": 168, "ECB": 168}
# Variacion contra el ultimo precio guardado sobre la cual el dato se marca
# como poco plausible (split de ticker, cambio de unidad, dato corrupto).
MAX_PLAUSIBLE_JUMP_PCT = 25.0
MACRO_SYMBOLS = frozenset({"TPM", "IPC", "DESEMPLEO"})


@dataclass(frozen=True)
class SourceCheck:
    source: str
    kind: SourceKind
    status: HealthStatus
    items: int = 0
    newest_at: datetime | None = None
    detail: str = ""


def check_news_sources(
    raw_news: Iterable[RawNewsItem],
    expected_sources: Iterable[str],
    now: datetime,
) -> list[SourceCheck]:
    """Un chequeo por fuente esperada: caida sin notas, degradada si todo es viejo."""
    by_source: dict[str, list[RawNewsItem]] = {}
    for item in raw_news:
        by_source.setdefault(item.source, []).append(item)

    checks: list[SourceCheck] = []
    for source in dict.fromkeys(expected_sources):
        items = by_source.get(source, [])
        if not items:
            checks.append(SourceCheck(source, SourceKind.NEWS, HealthStatus.DOWN, detail="sin notas"))
            continue
        newest = max(item.timestamp for item in items)
        max_age = timedelta(hours=NEWS_FRESHNESS_HOURS.get(source, DEFAULT_NEWS_FRESHNESS_HOURS))
        age_hours = int((now - newest).total_seconds() // 3600)
        if now - newest > max_age:
            status, detail = HealthStatus.DEGRADED, f"nota mas reciente de hace {age_hours} h"
        else:
            status, detail = HealthStatus.OK, ""
        checks.append(SourceCheck(source, SourceKind.NEWS, status, len(items), newest, detail))
    return checks


def check_market_snapshots(
    snapshots: Iterable[MarketSnapshot],
    expected_symbols: Iterable[str],
    previous_prices: dict[str, float],
) -> list[SourceCheck]:
    """Un chequeo por simbolo esperado: caido sin precio, degradado ante saltos absurdos."""
    by_symbol = {snapshot.symbol: snapshot for snapshot in snapshots}
    checks: list[SourceCheck] = []
    for symbol in dict.fromkeys(expected_symbols):
        kind = SourceKind.MACRO if symbol in MACRO_SYMBOLS else SourceKind.MARKET
        snapshot = by_symbol.get(symbol)
        if snapshot is None or snapshot.price is None:
            checks.append(SourceCheck(symbol, kind, HealthStatus.DOWN, detail="sin datos"))
            continue
        items = max(1, len(snapshot.history))
        previous = previous_prices.get(symbol)
        if kind is SourceKind.MARKET and previous:
            jump = abs(snapshot.price / previous - 1) * 100
            if jump > MAX_PLAUSIBLE_JUMP_PCT:
                detail = f"salto de {jump:.0f}% vs ultimo dato ({previous:,.2f} -> {snapshot.price:,.2f})"
                checks.append(SourceCheck(symbol, kind, HealthStatus.DEGRADED, items, detail=detail))
                continue
        checks.append(SourceCheck(symbol, kind, HealthStatus.OK, items))
    return checks


def next_state(
    previous_state: HealthStatus | None,
    previous_status: HealthStatus | None,
    status: HealthStatus,
) -> HealthStatus:
    """Estado reportado tras una corrida, con histeresis contra falsas alarmas.

    Una corrida mala aislada (timeout puntual) no cambia el estado: hacen
    falta dos seguidas. Una sola corrida buena basta para volver a "ok".
    """
    if status is HealthStatus.OK:
        return HealthStatus.OK
    if previous_status is not None and previous_status is not HealthStatus.OK:
        return status
    return previous_state or HealthStatus.OK


def unavailable_for_readers(checks: Iterable[SourceCheck], covered: Iterable[str] = ()) -> list[str]:
    """Fuentes sin datos en esta corrida, para la linea discreta del correo.

    `covered` son simbolos que igual se muestran con su ultimo dato valido
    (rotulado con fecha), asi que no se listan como ausentes.
    """
    skip = set(covered)
    return [check.source for check in checks if check.status is HealthStatus.DOWN and check.source not in skip]
