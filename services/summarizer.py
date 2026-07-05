from dataclasses import dataclass
from datetime import date

from services.market_snapshot import format_market_line
from storage.models import MarketSnapshot, NewsItem


@dataclass(frozen=True)
class GeneratedBrief:
    subject: str
    text_body: str


def _select_symbols(snapshots: list[MarketSnapshot], symbols: tuple[str, ...]) -> list[str]:
    by_symbol = {snapshot.symbol: snapshot for snapshot in snapshots}
    lines: list[str] = []
    for symbol in symbols:
        snapshot = by_symbol.get(symbol)
        if snapshot is None:
            continue
        if snapshot.price is None and snapshot.change_pct is None:
            continue
        lines.append(format_market_line(snapshot))
    return lines


def _top_news(news: list[NewsItem], region: str | None = None, limit: int = 3) -> list[str]:
    candidates = [item for item in news if region is None or item.region == region]
    candidates = sorted(candidates, key=lambda item: item.impact_score, reverse=True)[:limit]
    return [f"* {item.title} ({item.source})" for item in candidates]


def _section(title: str, lines: list[str]) -> str:
    body = "\n".join(lines) if lines else "* Sin datos relevantes disponibles al momento."
    return f"{title}\n{body}"


def _sentiment_lines(market_sentiment) -> list[str]:
    if market_sentiment is None:
        return []
    lines = [f"* {market_sentiment.label}: {market_sentiment.summary}"]
    lines.extend(f"* Driver: {driver}" for driver in market_sentiment.drivers[:3])
    return lines


def generate_morning_brief(
    current_date: date,
    snapshots: list[MarketSnapshot],
    news: list[NewsItem],
    market_sentiment=None,
) -> GeneratedBrief:
    subject = f"DMAC Morning Brief | Coyuntura Financiera | {current_date:%Y-%m-%d}"
    top = _top_news(news, limit=3)
    executive = top or ["* Sin titulares recientes de alta calidad en las fuentes configuradas."]

    sections = [
        _section("1. Resumen ejecutivo", executive),
        _section("2. Sentimiento de mercado", _sentiment_lines(market_sentiment)),
        _section(
            "3. Pulso de apertura",
            _select_symbols(snapshots, ("USDCLP", "COPPER", "IPSA", "TPM", "IPC"))
            + _select_symbols(snapshots, ("SP500", "NASDAQ100", "US10Y", "DXY", "GOLD", "WTI")),
        ),
        _section(
            "4. Que mirar hoy",
            [
                "* Eventos macro oficiales publicados durante la jornada.",
                "* Niveles en USD/CLP, cobre, S&P 500 y tasas de EE.UU.",
                "* Riesgos de titulares geopoliticos o de bancos centrales.",
            ],
        ),
        _section(
            "5. Lectura DMAC",
            [
                "* Hechos: los datos anteriores provienen de fuentes configuradas y pueden tener rezago.",
                "* Interpretacion: lectura preliminar y prudente; no constituye recomendacion de inversion.",
            ],
        ),
    ]
    return GeneratedBrief(subject, "\n\n".join(sections))


def generate_market_close(
    current_date: date,
    snapshots: list[MarketSnapshot],
    news: list[NewsItem],
    market_sentiment=None,
) -> GeneratedBrief:
    subject = f"DMAC Market Close | Cierre Financiero | {current_date:%Y-%m-%d}"
    relevant_moves = [
        format_market_line(snapshot)
        for snapshot in snapshots
        if snapshot.change_pct is not None and abs(snapshot.change_pct) >= 1.0
    ]
    sections = [
        _section("1. Resumen ejecutivo", _top_news(news, limit=3) or relevant_moves[:3]),
        _section("2. Sentimiento de mercado", _sentiment_lines(market_sentiment)),
        _section("3. Movimientos relevantes", relevant_moves[:6]),
        _section("4. Drivers del cierre", _top_news(news, limit=3)),
        _section(
            "5. Lectura DMAC",
            [
                "* Hechos: se observan precios o variaciones disponibles al cierre o ultima data publicada.",
                "* Interpretacion: los drivers son hipotesis razonables, no causalidad confirmada.",
            ],
        ),
        _section(
            "6. Que monitorear",
            [
                "* Confirmacion de datos oficiales y revision de titulares posteriores al cierre.",
                "* Apertura de Asia/Europa y reaccion en monedas/commodities.",
            ],
        ),
    ]
    return GeneratedBrief(subject, "\n\n".join(sections))


def generate_alert_text(item: NewsItem, snapshots: list[MarketSnapshot]) -> str:
    markets = _select_symbols(snapshots, ("USDCLP", "COPPER", "SP500", "NASDAQ100", "US10Y", "DXY", "GOLD"))
    return "\n".join(
        [
            f"Evento: {item.title}",
            f"Zona afectada: {item.region}",
            "Mercados afectados:",
            *(f"* {line}" for line in markets),
            "Movimiento observado: revisar variaciones anteriores y fuente primaria.",
            f"Lectura preliminar: noticia clasificada como {item.topic}.",
            "Que monitorear: confirmacion por fuentes oficiales, reaccion de activos y nuevos titulares.",
            "Nota de cautela: alerta preliminar, no constituye recomendacion de inversion.",
        ]
    )
