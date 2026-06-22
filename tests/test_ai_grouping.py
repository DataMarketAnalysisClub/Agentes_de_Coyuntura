from datetime import UTC, datetime

from services.ai.grouping import (
    group_by_country,
    group_by_region,
    group_by_topic,
    infer_country,
    limit_groups,
    select_and_prepare,
    to_routed_input,
    urls_for,
)
from storage.models import NewsItem


def _make_news(count: int = 5) -> list[NewsItem]:
    return [
        NewsItem(
            timestamp=datetime.now(UTC),
            source=f"Source {i}",
            title=f"{'Chile ' if i == 0 else 'Fed '}title {i}",
            url=f"https://example.com/{i}",
            summary=f"Summary {i}",
            region="Chile" if i == 0 else "EE.UU.",
            topic="tasas" if i % 2 == 0 else "commodities",
            impact_score=10 - i,
        )
        for i in range(count)
    ]


class TestGrouping:
    def test_infer_country_chile(self) -> None:
        assert infer_country("Hacienda anuncia presupuesto") == "Chile"

    def test_infer_country_us(self) -> None:
        assert infer_country("Fed cuts rates") == "Estados Unidos"

    def test_infer_country_eurozone(self) -> None:
        assert infer_country("ECB holds rates") == "Eurozona"

    def test_infer_country_brazil(self) -> None:
        assert infer_country("Bovespa cae") == "Brasil"

    def test_infer_country_none(self) -> None:
        assert infer_country("Generic news about markets") is None

    def test_to_routed_input_preserves_fields(self) -> None:
        news = _make_news(1)[0]
        routed = to_routed_input(news)
        assert routed.id == news.url
        assert routed.title == news.title
        assert routed.url == news.url
        assert routed.region == news.region

    def test_select_and_prepare_orders_by_impact(self) -> None:
        news = _make_news(5)
        routed = select_and_prepare(news, max_news=3)
        assert len(routed) == 3
        assert routed[0].impact_score >= routed[1].impact_score

    def test_select_and_prepare_limits(self) -> None:
        news = _make_news(10)
        routed = select_and_prepare(news, max_news=5)
        assert len(routed) == 5

    def test_group_by_region(self) -> None:
        routed = select_and_prepare(_make_news(5), max_news=5)
        groups = group_by_region(routed)
        assert "Chile" in groups
        assert "EE.UU." in groups

    def test_group_by_country_falls_back_to_region(self) -> None:
        routed = select_and_prepare(_make_news(5), max_news=5)
        groups = group_by_country(routed)
        assert len(groups) >= 1

    def test_group_by_topic(self) -> None:
        routed = select_and_prepare(_make_news(5), max_news=5)
        groups = group_by_topic(routed)
        assert "tasas" in groups
        assert "commodities" in groups

    def test_limit_groups(self) -> None:
        routed = select_and_prepare(_make_news(10), max_news=10)
        limited = limit_groups(routed, max_per_group=2)
        by_topic = group_by_topic(limited)
        for items in by_topic.values():
            assert len(items) <= 2

    def test_urls_for(self) -> None:
        routed = select_and_prepare(_make_news(3), max_news=3)
        urls = urls_for(routed)
        assert len(urls) == 3
        assert all(u.startswith("https://") for u in urls)

    def test_does_not_mutate_news_items(self) -> None:
        news = _make_news(3)
        original_scores = [n.impact_score for n in news]
        select_and_prepare(news, max_news=3)
        assert [n.impact_score for n in news] == original_scores
