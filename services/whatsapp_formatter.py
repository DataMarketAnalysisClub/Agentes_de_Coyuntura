from datetime import date

from services.market_snapshot import format_market_line
from storage.models import MarketSnapshot, NewsItem

WATCH_SYMBOLS = ("USDCLP", "COPPER", "SP500", "VOO", "GOLD", "IPSA")


def _snapshot_map(snapshots: list[MarketSnapshot]) -> dict[str, MarketSnapshot]:
    return {snapshot.symbol: snapshot for snapshot in snapshots}


def format_whatsapp_brief(
    title: str,
    current_date: date,
    snapshots: list[MarketSnapshot],
    news: list[NewsItem],
) -> str:
    """Generate a compact WhatsApp-ready market brief."""

    snapshot_by_symbol = _snapshot_map(snapshots)
    top_news = sorted(news, key=lambda item: item.impact_score, reverse=True)[:3]
    summary_lines = [f"* {item.title}" for item in top_news] or ["* Sin titulares recientes de alto impacto."]

    market_lines = []
    for symbol in WATCH_SYMBOLS:
        snapshot = snapshot_by_symbol.get(symbol)
        if snapshot:
            market_lines.append(f"* {format_market_line(snapshot)}")
    if not market_lines:
        market_lines.append("* Datos de mercado no disponibles al momento.")

    watch_lines = [
        "1. Comunicados oficiales y datos macro del dia.",
        "2. Movimientos en USD/CLP, cobre y tasas externas.",
        "3. Noticias que puedan cambiar el apetito por riesgo.",
    ]

    return "\n".join(
        [
            f"DMAC {title} | {current_date:%d-%m-%Y}",
            "",
            "Resumen:",
            *summary_lines,
            "",
            "Mercados:",
            *market_lines,
            "",
            "Que mirar:",
            *watch_lines,
            "",
            "Nota: analisis preliminar sujeto a nueva informacion.",
        ]
    )
