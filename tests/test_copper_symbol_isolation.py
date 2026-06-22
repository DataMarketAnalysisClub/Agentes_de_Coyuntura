"""Tests that the internal yfinance ticker HG=F never leaks into IA payloads
or editorial outputs. The IA and outputs should always use the editorial
symbol COPPER, not the yfinance internal ticker.
"""

from datetime import UTC, datetime

from data_sources.yfinance_client import DEFAULT_ASSETS
from services.ai.chart_renderer import available_chart_ids, render_chart_to_html
from services.ai.schemas import AiChartSpec, AiMarketSnapshotInput
from storage.models import MarketSnapshot


class TestCopperSymbolIsolation:
    def test_copper_uses_hgf_internally(self) -> None:
        """COPPER asset should map to HG=F internally in yfinance_client only."""
        copper = next(a for a in DEFAULT_ASSETS if a.symbol == "COPPER")
        assert copper.yf_ticker == "HG=F"
        assert copper.symbol == "COPPER"
        assert copper.name == "Cobre"

    def test_market_snapshot_uses_copper_not_hgf(self) -> None:
        """MarketSnapshot should use symbol COPPER, never HG=F."""
        snap = MarketSnapshot(
            timestamp=datetime.now(UTC),
            symbol="COPPER",
            name="Cobre",
            price=4.5,
            change_pct=1.0,
            source="yfinance",
        )
        assert snap.symbol == "COPPER"
        assert "HG=F" not in snap.symbol
        assert "HG=F" not in snap.name

    def test_ai_market_snapshot_input_uses_copper(self) -> None:
        """AiMarketSnapshotInput should use symbol COPPER."""
        snap = MarketSnapshot(
            timestamp=datetime.now(UTC),
            symbol="COPPER",
            name="Cobre",
            price=4.5,
            change_pct=1.0,
            source="yfinance",
        )
        ai_input = AiMarketSnapshotInput(
            symbol=snap.symbol,
            name=snap.name,
            price=snap.price,
            change_pct=snap.change_pct,
            source=snap.source,
        )
        payload = ai_input.model_dump(mode="json")
        payload_str = str(payload)
        assert "COPPER" in payload_str
        assert "HG=F" not in payload_str

    def test_chart_change_pct_uses_copper_name(self) -> None:
        """change_pct_bar chart should display 'Cobre' or 'COPPER', not HG=F."""
        snaps = [
            MarketSnapshot(
                timestamp=datetime.now(UTC),
                symbol="COPPER",
                name="Cobre",
                price=4.5,
                change_pct=2.0,
                source="yfinance",
            ),
        ]
        spec = AiChartSpec(
            chart_id="change_pct_bar",
            chart_type="bar_change_pct",
            title="Variacion %",
        )
        html = render_chart_to_html(spec, snaps, [])
        assert "Cobre" in html or "COPPER" in html
        assert "HG=F" not in html

    def test_chart_assets_table_uses_copper(self) -> None:
        """assets_table chart should display COPPER, not HG=F."""
        snaps = [
            MarketSnapshot(
                timestamp=datetime.now(UTC),
                symbol="COPPER",
                name="Cobre",
                price=4.5,
                change_pct=2.0,
                source="yfinance",
            ),
        ]
        spec = AiChartSpec(
            chart_id="assets_table",
            chart_type="table_assets",
            title="Activos",
        )
        html = render_chart_to_html(spec, snaps, [])
        assert "COPPER" in html
        assert "HG=F" not in html

    def test_hgf_only_in_yfinance_client(self) -> None:
        """HG=F should only appear in data_sources/yfinance_client.py."""
        import subprocess
        result = subprocess.run(
            ["grep", "-rl", "HG=F", "--include=*.py", "."],
            capture_output=True,
            text=True,
            check=False,
        )
        files_with_hgf = [f.lstrip("./") for f in result.stdout.strip().split("\n") if f]
        allowed = {"data_sources/yfinance_client.py", "tests/test_copper_symbol_isolation.py"}
        leaked = {f for f in files_with_hgf if f not in allowed}
        assert not leaked, f"HG=F found in unexpected files: {leaked}"

    def test_available_chart_ids_with_copper_snapshot(self) -> None:
        """available_chart_ids should include change_pct_bar when COPPER has data."""
        snaps = [
            MarketSnapshot(
                timestamp=datetime.now(UTC),
                symbol="COPPER",
                name="Cobre",
                price=4.5,
                change_pct=2.0,
                source="yfinance",
            ),
        ]
        ids = available_chart_ids(snaps, [])
        assert "change_pct_bar" in ids
        assert "assets_table" in ids
