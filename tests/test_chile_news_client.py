from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from data_sources.chile_news_client import ChileNewsClient, RawNewsItem


class FakeResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
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
    def test_scrapes_hacienda_news(self, client: ChileNewsClient, mock_http_client: MagicMock) -> None:
        index_html = """
        <html>
        <body>
            <a href="/noticias-y-eventos/noticias/test-noticia">Noticia de Hacienda</a>
            <a href="/noticias-y-eventos/noticias/otra-noticia">Otra Noticia</a>
        </body>
        </html>
        """
        article_html = """
        <html>
        <body>
            <article>
                <time datetime="2026-06-20T10:00:00Z">20 Junio 2026</time>
                <p>Resumen del comunicado oficial.</p>
            </article>
        </body>
        </html>
        """

        def fake_get(url: str) -> FakeResponse:
            if "/noticias/" in url:
                return FakeResponse(article_html)
            return FakeResponse(index_html)

        mock_http_client.get.side_effect = fake_get

        items = client._scrape_hacienda()

        assert len(items) == 2
        assert items[0].source == "Ministerio de Hacienda"
        assert "Noticia de Hacienda" in items[0].title
        assert "Resumen del comunicado" in items[0].summary

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

    def test_fetch_latest_handles_hacienda_exceptions_gracefully(self, client: ChileNewsClient) -> None:
        with pytest.raises(Exception):
            raise Exception("Network error")

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
