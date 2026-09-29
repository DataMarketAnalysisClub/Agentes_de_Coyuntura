from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from data_sources.chile_news_client import (
    LATERCERA_PULSO_HTML_URL,
    LATERCERA_PULSO_RSS_URL,
    ChileNewsClient,
    RawNewsItem,
)

LATERCERA_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Pulso</title>
<item>
  <title>Dolar cierra al alza</title>
  <link>https://www.latercera.com/pulso/noticia/dolar-cierra-al-alza/</link>
  <description><![CDATA[<p>El dolar subio &amp; el cobre cayo.</p>]]></description>
  <pubDate>Mon, 28 Sep 2026 18:34:03 +0000</pubDate>
</item>
<item>
  <title>Nota de otra seccion</title>
  <link>https://www.latercera.com/nacional/noticia/otra/</link>
  <pubDate>Mon, 28 Sep 2026 18:00:00 +0000</pubDate>
</item>
</channel></rss>"""


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.content = text.encode("utf-8")
        self.status_code = status_code

    def raise_for_status(self) -> None:
        pass


@pytest.fixture
def mock_http_client() -> MagicMock:
    return MagicMock()


@pytest.fixture
def client(mock_http_client: MagicMock) -> ChileNewsClient:
    return ChileNewsClient(http_client=mock_http_client)


class TestChileNewsClient:
    def test_scrapes_latercera_pulso(self, client: ChileNewsClient, mock_http_client: MagicMock) -> None:
        html = """
        <html>
        <body>
            <div class="story-card">
                <h2 class="headline">Titular Pulso</h2>
                <a href="/pulso/noticia/test-pulso">Leer más</a>
                <p class="c-deck">Resumen de economia</p>
            </div>
            <div class="c-post">
                <h3>Otro Titular</h3>
                <a href="/pulso/noticia/otra-noticia">Enlace</a>
                <p class="summary">Otro resumen</p>
            </div>
        </body>
        </html>
        """

        mock_http_client.get.return_value = FakeResponse(html)

        items = client._scrape_latercera_pulso()

        assert len(items) >= 1
        assert items[0].source == "La Tercera Pulso"

    def test_fetch_latest_uses_latercera_rss_first(self, client: ChileNewsClient, mock_http_client: MagicMock) -> None:
        mock_http_client.get.return_value = FakeResponse(LATERCERA_RSS)

        items = client.fetch_latest()

        requested_urls = [call.args[0] for call in mock_http_client.get.call_args_list]
        assert requested_urls == [LATERCERA_PULSO_RSS_URL]
        assert [item.title for item in items] == ["Dolar cierra al alza"]
        assert items[0].source == "La Tercera Pulso"
        assert items[0].summary == "El dolar subio & el cobre cayo."
        assert items[0].timestamp == datetime(2026, 9, 28, 18, 34, 3, tzinfo=UTC)

    def test_fetch_latest_falls_back_to_html_when_rss_is_empty(
        self, client: ChileNewsClient, mock_http_client: MagicMock
    ) -> None:
        mock_http_client.get.return_value = FakeResponse("<html></html>")

        client.fetch_latest()

        requested_urls = [call.args[0] for call in mock_http_client.get.call_args_list]
        assert requested_urls == [LATERCERA_PULSO_RSS_URL, LATERCERA_PULSO_HTML_URL]

    def test_html_scraper_skips_duplicate_urls(self, client: ChileNewsClient) -> None:
        html = """
        <article>
          <div class="story-card">
            <h2>Titular</h2><a href="/pulso/noticia/unica">Leer</a>
          </div>
        </article>
        """

        articles = client._extract_latercera_articles(html)

        assert len(articles) == 1

    def test_raw_news_item_structure(self) -> None:
        item = RawNewsItem(
            timestamp=datetime.now(UTC),
            source="Test Source",
            title="Test Title",
            url="https://example.com",
            summary="Test summary",
        )
        assert item.source == "Test Source"
        assert item.title == "Test Title"
        assert item.url == "https://example.com"
        assert item.summary == "Test summary"
        assert item.timestamp.tzinfo is not None

    def test_client_can_be_instantiated_without_http_client(self) -> None:
        client = ChileNewsClient()
        assert client._http_client is None

    def test_get_client_returns_provided_client(self, mock_http_client: MagicMock) -> None:
        client = ChileNewsClient(http_client=mock_http_client)
        assert client._get_client() is mock_http_client
