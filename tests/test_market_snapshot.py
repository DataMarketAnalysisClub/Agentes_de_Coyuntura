from data_sources.yfinance_client import Quote
from services.market_snapshot import MarketSnapshotService


class MockMarketClient:
    def fetch_quotes(self) -> list[Quote]:
        return [Quote("USDCLP", "USD/CLP", 930.0, 0.5, "mock", history=(920.0, 925.0, 930.0))]


class FailingMarketClient:
    def fetch_quotes(self) -> list[Quote]:
        raise RuntimeError("provider down")


class EmptyMarketClient:
    def fetch_quotes(self) -> list[Quote]:
        return [
            Quote("SP500", "S&P 500", None, None, "yfinance"),
            Quote("GOLD", "Oro", None, None, "yfinance"),
        ]


class FallbackMarketClient:
    def fetch_quotes(self) -> list[Quote]:
        return [
            Quote("SP500", "S&P 500", 7440.43, 1.18, "fallback_provider"),
            Quote("WTI", "Petroleo WTI", 68.5, -0.4, "fallback_provider"),
        ]


class MockBCentralClient:
    def __init__(self, fx_quote: Quote | None = None) -> None:
        self.fx_quote = fx_quote
        self.fx_requests: list[tuple[str, str]] = []

    def fetch_policy_rate(self) -> float | None:
        return None

    def fetch_inflation(self) -> float | None:
        return None

    def fetch_unemployment(self) -> float | None:
        return 8.7

    def fetch_fx_quote(self, series_id: str, symbol: str, name: str) -> Quote | None:
        self.fx_requests.append((series_id, symbol))
        return self.fx_quote


def test_market_snapshot_collects_mock_data() -> None:
    service = MarketSnapshotService(MockMarketClient(), MockBCentralClient())

    snapshots = service.collect()

    assert any(snapshot.symbol == "USDCLP" and snapshot.price == 930.0 for snapshot in snapshots)
    usdclp = next(snapshot for snapshot in snapshots if snapshot.symbol == "USDCLP")
    assert usdclp.history == (920.0, 925.0, 930.0)
    assert any(snapshot.symbol == "TPM" for snapshot in snapshots)
    assert any(snapshot.symbol == "IPC" for snapshot in snapshots)


def test_market_snapshot_continues_when_provider_fails() -> None:
    service = MarketSnapshotService(FailingMarketClient(), MockBCentralClient())

    snapshots = service.collect()

    assert [snapshot.symbol for snapshot in snapshots] == ["TPM", "IPC", "DESEMPLEO"]


def test_market_snapshot_uses_fallback_when_primary_has_no_values() -> None:
    service = MarketSnapshotService(EmptyMarketClient(), MockBCentralClient(), FallbackMarketClient())

    snapshots = service.collect()

    by_symbol = {snapshot.symbol: snapshot for snapshot in snapshots}
    assert by_symbol["SP500"].price == 7440.43
    assert by_symbol["SP500"].change_pct == 1.18
    assert by_symbol["SP500"].source == "fallback_provider"
    assert by_symbol["GOLD"].price is None
    assert by_symbol["WTI"].price == 68.5


USDPEN_QUOTE = Quote("USDPEN", "USD/PEN", 3.71, -0.2, "bcentral", history=(3.70, 3.72, 3.71))


def test_market_snapshot_adds_bcentral_fx_and_unemployment() -> None:
    bcentral = MockBCentralClient(USDPEN_QUOTE)
    service = MarketSnapshotService(MockMarketClient(), bcentral)

    snapshots = service.collect()

    symbols = [snapshot.symbol for snapshot in snapshots]
    assert symbols == ["USDCLP", "USDPEN", "TPM", "IPC", "DESEMPLEO"]
    by_symbol = {snapshot.symbol: snapshot for snapshot in snapshots}
    assert by_symbol["USDPEN"].source == "bcentral"
    assert by_symbol["USDPEN"].history == (3.70, 3.72, 3.71)
    assert by_symbol["DESEMPLEO"].price == 8.7
    assert bcentral.fx_requests == [("F072.PEN.USD.N.O.D", "USDPEN")]


def test_bcentral_fx_does_not_mask_primary_provider_failure() -> None:
    service = MarketSnapshotService(EmptyMarketClient(), MockBCentralClient(USDPEN_QUOTE), FallbackMarketClient())

    snapshots = service.collect()

    by_symbol = {snapshot.symbol: snapshot for snapshot in snapshots}
    assert by_symbol["SP500"].source == "fallback_provider"
    assert by_symbol["USDPEN"].source == "bcentral"
