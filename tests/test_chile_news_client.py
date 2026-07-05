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

    def test_fetch_latest_only_uses_latercera_pulso(self, client: ChileNewsClient, mock_http_client: MagicMock) -> None:
        mock_http_client.get.return_value = FakeResponse("<html></html>")

        client.fetch_latest()

        requested_urls = [call.args[0] for call in mock_http_client.get.call_args_list]
        assert requested_urls == ["https://www.latercera.com/canal/pulso/"]

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
