from data_sources.yfinance_client import Quote
from services.market_snapshot import MarketSnapshotService


class MockMarketClient:
    def fetch_quotes(self) -> list[Quote]:
        return [Quote("USDCLP", "USD/CLP", 930.0, 0.5, "mock")]


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
            Quote("SP500", "S&P 500", 7440.43, 1.18, "google_finance"),
            Quote("WTI", "Petroleo WTI", 68.5, -0.4, "google_finance"),
        ]


class MockBCentralClient:
    def fetch_policy_rate(self) -> float | None:
        return None

    def fetch_inflation(self) -> float | None:
        return None


def test_market_snapshot_collects_mock_data() -> None:
    service = MarketSnapshotService(MockMarketClient(), MockBCentralClient())

    snapshots = service.collect()

    assert any(snapshot.symbol == "USDCLP" and snapshot.price == 930.0 for snapshot in snapshots)
    assert any(snapshot.symbol == "TPM" for snapshot in snapshots)
    assert any(snapshot.symbol == "IPC" for snapshot in snapshots)


def test_market_snapshot_continues_when_provider_fails() -> None:
    service = MarketSnapshotService(FailingMarketClient(), MockBCentralClient())

    snapshots = service.collect()

    assert [snapshot.symbol for snapshot in snapshots] == ["TPM", "IPC"]


def test_market_snapshot_uses_fallback_when_primary_has_no_values() -> None:
    service = MarketSnapshotService(EmptyMarketClient(), MockBCentralClient(), FallbackMarketClient())

    snapshots = service.collect()

    by_symbol = {snapshot.symbol: snapshot for snapshot in snapshots}
    assert by_symbol["SP500"].price == 7440.43
    assert by_symbol["SP500"].change_pct == 1.18
    assert by_symbol["SP500"].source == "google_finance"
    assert by_symbol["GOLD"].price is None
    assert by_symbol["WTI"].price == 68.5
