from dataclasses import dataclass

from storage.models import MarketSnapshot


@dataclass(frozen=True)
class MarketSentiment:
    label: str
    score: int
    summary: str
    drivers: list[str]
    source: str


RISK_ON_SYMBOLS = {"SP500", "VOO", "NASDAQ100", "IPSA", "BOVESPA", "MEXIPC", "COPPER"}
RISK_OFF_SYMBOLS = {"VIX", "DXY", "US10Y"}


def collect_market_sentiment(snapshots: list[MarketSnapshot]) -> MarketSentiment:
    return build_market_sentiment(snapshots)


def build_market_sentiment(snapshots: list[MarketSnapshot]) -> MarketSentiment:
    contributions: list[tuple[str, float, str]] = []

    for snapshot in snapshots:
        if snapshot.change_pct is None:
            continue
        if snapshot.symbol in RISK_ON_SYMBOLS:
            contributions.append((snapshot.name, snapshot.change_pct, snapshot.source))
        elif snapshot.symbol in RISK_OFF_SYMBOLS:
            contributions.append((snapshot.name, -snapshot.change_pct, snapshot.source))

    if not contributions:
        return MarketSentiment(
            label="Neutral",
            score=50,
            summary="No hay suficientes datos de mercado para inferir sentimiento.",
            drivers=[],
            source="sin datos suficientes",
        )

    weighted = sum(_clamp(value, -3.0, 3.0) for _, value, _ in contributions)
    average = weighted / len(contributions)
    score = int(round(_clamp(50 + average * 14, 0, 100)))
    label = _label_for_score(score)
    drivers = _drivers(contributions)
    source = "yfinance"

    summary = _summary(label, score, drivers)
    return MarketSentiment(label=label, score=score, summary=summary, drivers=drivers, source=source)


def _drivers(contributions: list[tuple[str, float, str]]) -> list[str]:
    ordered = sorted(contributions, key=lambda item: abs(item[1]), reverse=True)
    return [f"{name}: {value:+.2f}%" for name, value, _ in ordered[:4]]


def _label_for_score(score: int) -> str:
    if score >= 70:
        return "Riesgo positivo"
    if score >= 56:
        return "Levemente positivo"
    if score <= 30:
        return "Riesgo defensivo"
    if score <= 44:
        return "Levemente defensivo"
    return "Neutral"


def _summary(label: str, score: int, drivers: list[str]) -> str:
    if not drivers:
        return f"Sentimiento {label.lower()} ({score}/100), sin drivers dominantes."
    return f"Sentimiento {label.lower()} ({score}/100), explicado principalmente por {', '.join(drivers[:2])}."


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
