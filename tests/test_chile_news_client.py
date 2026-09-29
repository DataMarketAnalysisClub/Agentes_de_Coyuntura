from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from data_sources.chile_news_client import (
    DF_RSS_URL,
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


DF_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:df="http://www.w3.org/TR/html4/"><channel><title>Diario Financiero Online</title>
<item>
  <pubDate>Tue, 29 Sep 2026 13:05:54 GMT</pubDate>
  <title>Dolar abre a la baja por el cobre</title>
  <category>Mercados</category>
  <link>http://www.df.cl/mercados/bolsa-monedas/dolar-abre-a-la-baja</link>
  <description>El peso chileno se aprecia.</description>
</item>
<item>
  <pubDate>Tue, 29 Sep 2026 12:00:00 GMT</pubDate>
  <title>Carta: el dolar y nosotros</title>
  <category>Opinion</category>
  <link>http://www.df.cl/opinion/cartas/el-dolar-y-nosotros</link>
</item>
<item>
  <pubDate>Tue, 29 Sep 2026 11:00:00 GMT</pubDate>
  <title>Puerto de Valparaiso amplia su terminal</title>
  <category>Regiones</category>
  <link>http://www.df.cl/regiones/valparaiso/puerto-amplia-terminal</link>
</item>
</channel></rss>"""


def _responses_by_url(responses: dict[str, str]):
    def _get(url: str, *args, **kwargs):
        return FakeResponse(responses.get(url, ""))

    return _get


def _requested_urls(mock_http_client: MagicMock) -> list[str]:
    return [call.args[0] for call in mock_http_client.get.call_args_list]


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
        mock_http_client.get.side_effect = _responses_by_url({LATERCERA_PULSO_RSS_URL: LATERCERA_RSS})

        items = client.fetch_latest()

        assert LATERCERA_PULSO_HTML_URL not in _requested_urls(mock_http_client)
        assert [item.title for item in items] == ["Dolar cierra al alza"]
        assert items[0].source == "La Tercera Pulso"
        assert items[0].summary == "El dolar subio & el cobre cayo."
        assert items[0].timestamp == datetime(2026, 9, 28, 18, 34, 3, tzinfo=UTC)

    def test_fetch_latest_falls_back_to_html_when_rss_is_empty(
        self, client: ChileNewsClient, mock_http_client: MagicMock
    ) -> None:
        mock_http_client.get.side_effect = _responses_by_url({LATERCERA_PULSO_HTML_URL: "<html></html>"})

        client.fetch_latest()

        requested = [url for url in _requested_urls(mock_http_client) if url != DF_RSS_URL]
        assert requested == [LATERCERA_PULSO_RSS_URL, LATERCERA_PULSO_HTML_URL]

    def test_fetch_latest_includes_diario_financiero_news_sections_only(
        self, client: ChileNewsClient, mock_http_client: MagicMock
    ) -> None:
        mock_http_client.get.side_effect = _responses_by_url(
            {LATERCERA_PULSO_RSS_URL: LATERCERA_RSS, DF_RSS_URL: DF_RSS}
        )

        items = client.fetch_latest()

        df_items = [item for item in items if item.source == "Diario Financiero"]
        assert [item.title for item in df_items] == ["Dolar abre a la baja por el cobre"]
        assert df_items[0].url == "https://www.df.cl/mercados/bolsa-monedas/dolar-abre-a-la-baja"
        assert df_items[0].timestamp == datetime(2026, 9, 29, 13, 5, 54, tzinfo=UTC)
        assert any(item.source == "La Tercera Pulso" for item in items)

    def test_fetch_latest_continues_when_diario_financiero_fails(
        self, client: ChileNewsClient, mock_http_client: MagicMock
    ) -> None:
        def _get(url: str, *args, **kwargs):
            if url == DF_RSS_URL:
                raise RuntimeError("df down")
            return FakeResponse(LATERCERA_RSS)

        mock_http_client.get.side_effect = _get

        items = client.fetch_latest()

        assert [item.source for item in items] == ["La Tercera Pulso"]

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
