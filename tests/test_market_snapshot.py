from data_sources.yfinance_client import Quote
from services.market_snapshot import MarketSnapshotService


class MockMarketClient:
    def fetch_quotes(self) -> list[Quote]:
        return [Quote("USDCLP", "USD/CLP", 930.0, 0.5, "mock")]


class FailingMarketClient:
    def fetch_quotes(self) -> list[Quote]:
        raise RuntimeError("provider down")


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
