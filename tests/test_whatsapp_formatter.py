from datetime import UTC, date, datetime

from services.whatsapp_formatter import format_whatsapp_brief
from storage.models import MarketSnapshot, NewsItem


def test_format_whatsapp_brief_contains_required_sections() -> None:
    snapshots = [MarketSnapshot(datetime.now(UTC), "USDCLP", "USD/CLP", 930.0, 0.5, "mock")]
    news = [
        NewsItem(
            timestamp=datetime.now(UTC),
            source="BLS",
            title="US employment data surprises markets",
            url="https://example.com/jobs",
            summary="",
            region="EE.UU.",
            topic="empleo",
            impact_score=7,
        )
    ]

    body = format_whatsapp_brief("Morning Brief", date(2026, 6, 18), snapshots, news)

    assert "DMAC Morning Brief | 18-06-2026" in body
    assert "Resumen:" in body
    assert "Mercados:" in body
    assert "Que mirar:" in body
    assert "USD/CLP" in body
