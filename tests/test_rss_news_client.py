from datetime import UTC, datetime

import httpx

from app.config import Settings
from data_sources.rss_news_client import RssFeed, RssNewsClient, fetch_feed, parse_feed

INVESTING_STYLE_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Investing</title>
<item>
  <title>U.S. stocks slip</title>
  <link>https://www.investing.com/news/stock-market-news/us-stocks-slip-1</link>
  <pubDate>2026-09-28 19:32:38</pubDate>
</item>
</channel></rss>"""

HTML_SUMMARY_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Feed</title>
<item>
  <title>Fed &amp; tasas</title>
  <link>https://example.com/a</link>
  <description><![CDATA[<p>La <b>Fed</b> mantuvo   la tasa.</p>]]></description>
  <pubDate>Mon, 28 Sep 2026 18:34:03 +0000</pubDate>
</item>
</channel></rss>"""


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.content = text.encode("utf-8")


class FakeHttpClient:
    def __init__(self, responses: dict[str, str]) -> None:
        self.responses = responses
        self.requested: list[str] = []

    def get(self, url: str) -> FakeResponse:
        self.requested.append(url)
        if url not in self.responses:
            raise httpx.ConnectError("boom")
        return FakeResponse(self.responses[url])


def test_parse_feed_reads_non_rfc822_dates() -> None:
    items = parse_feed(INVESTING_STYLE_RSS, "Investing.com")

    assert len(items) == 1
    assert items[0].timestamp == datetime(2026, 9, 28, 19, 32, 38, tzinfo=UTC)


def test_parse_feed_strips_html_from_title_and_summary() -> None:
    items = parse_feed(HTML_SUMMARY_RSS, "Feed")

    assert items[0].title == "Fed & tasas"
    assert items[0].summary == "La Fed mantuvo la tasa."


def test_fetch_latest_skips_failed_feed_and_keeps_order() -> None:
    client = RssNewsClient(settings=Settings(rss_feeds="https://ok.example/rss,https://down.example/rss,https://ok2.example/rss"))
    fake_http = FakeHttpClient(
        {
            "https://ok.example/rss": INVESTING_STYLE_RSS,
            "https://ok2.example/rss": HTML_SUMMARY_RSS,
        }
    )
    client.http_client_for = lambda feed: fake_http  # type: ignore[method-assign]

    items = client.fetch_latest()

    assert [item.source for item in items] == ["ok.example", "ok2.example"]
    # El feed caido se pide una sola vez (sin segundo intento via feedparser.parse(url)).
    assert fake_http.requested.count("https://down.example/rss") == 1


def test_fetch_latest_with_no_feeds_returns_empty() -> None:
    client = RssNewsClient(settings=Settings())
    client.configured_feeds = lambda: ()  # type: ignore[method-assign]

    assert client.fetch_latest() == []


def test_http_client_is_per_host() -> None:
    client = RssNewsClient(settings=Settings())
    fed = client.http_client_for(RssFeed("Fed", "https://www.federalreserve.gov/feeds/a.xml"))
    fed_again = client.http_client_for(RssFeed("Fed", "https://www.federalreserve.gov/feeds/b.xml"))
    ecb = client.http_client_for(RssFeed("ECB", "https://www.ecb.europa.eu/rss/press.html"))

    assert fed is fed_again
    assert fed is not ecb
    assert fed.name == "rss:www.federalreserve.gov"


class ConditionalResponse:
    def __init__(self, status_code: int, text: str = "", headers: dict[str, str] | None = None) -> None:
        self.status_code = status_code
        self.content = text.encode("utf-8")
        self.headers = headers or {}


class ConditionalHttpClient:
    """Responde 304 si llegan los validadores de la respuesta anterior."""

    def __init__(self, text: str, headers: dict[str, str]) -> None:
        self.text = text
        self.headers = headers
        self.sent_headers: list[dict[str, str]] = []

    def get(self, url: str, headers: dict[str, str] | None = None) -> ConditionalResponse:
        self.sent_headers.append(dict(headers or {}))
        if headers and headers.get("If-None-Match") == self.headers.get("etag"):
            return ConditionalResponse(304)
        return ConditionalResponse(200, self.text, self.headers)


def test_fetch_feed_reuses_items_on_304() -> None:
    http = ConditionalHttpClient(HTML_SUMMARY_RSS, {"etag": '"v1"', "last-modified": "Mon, 28 Sep 2026 18:34:03 GMT"})

    first = fetch_feed(http, "https://example.com/rss", "Feed")
    second = fetch_feed(http, "https://example.com/rss", "Feed")

    assert http.sent_headers[0] == {}
    assert http.sent_headers[1] == {"If-None-Match": '"v1"', "If-Modified-Since": "Mon, 28 Sep 2026 18:34:03 GMT"}
    assert second == first
    assert second[0].title == "Fed & tasas"


def test_fetch_feed_without_validators_always_downloads() -> None:
    http = ConditionalHttpClient(HTML_SUMMARY_RSS, {})

    fetch_feed(http, "https://example.com/df", "DF")
    fetch_feed(http, "https://example.com/df", "DF")

    assert http.sent_headers == [{}, {}]


def test_http_client_returns_304_without_raising() -> None:
    from app.http_client import ResilientHttpClient

    client = ResilientHttpClient(name="test-304", retries=1)
    client._client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(304)))

    assert client.get("https://example.com/rss", headers={"If-None-Match": '"v1"'}).status_code == 304
