from data_sources.google_finance_client import (
    GoogleFinanceMarketItem,
    GoogleFinanceQuoteClient,
    parse_market_summary,
)


class MockGoogleFinanceClient:
    def fetch_market_summary(self) -> list[GoogleFinanceMarketItem]:
        return [
            GoogleFinanceMarketItem("S&P 500", 7440.43, 1.18),
            GoogleFinanceMarketItem("Nasdaq", 25000.0, 0.8),
            GoogleFinanceMarketItem("VIX", 17.65, -4.13),
        ]


def test_parse_market_summary_extracts_watched_markets() -> None:
    html = """
    <html><body>
      <div>S&amp;P 500</div><div>7,440.43</div><div>+1.18%</div>
      <div>VIX</div><div>17.65</div><div>-4.13%</div>
      <div>Unwatched</div><div>1.00</div><div>+9.00%</div>
    </body></html>
    """

    items = parse_market_summary(html)

    by_name = {item.name: item for item in items}
    assert by_name["S&P 500"].price == 7440.43
    assert by_name["S&P 500"].change_pct == 1.18
    assert by_name["VIX"].change_pct == -4.13
    assert "Unwatched" not in by_name


def test_google_finance_quote_client_maps_supported_markets() -> None:
    quotes = GoogleFinanceQuoteClient(MockGoogleFinanceClient()).fetch_quotes()

    by_symbol = {quote.symbol: quote for quote in quotes}
    assert by_symbol["SP500"].price == 7440.43
    assert by_symbol["SP500"].source == "google_finance"
    assert by_symbol["NASDAQ100"].change_pct == 0.8
    assert "VIX" not in by_symbol
