from datetime import UTC, datetime, timedelta

from services.email_charts import render_assets_table
from services.email_formatter import build_email_html
from services.market_snapshot import format_market_line, market_display_names, with_last_good_prices
from storage.models import MarketSnapshot

NOW = datetime(2026, 9, 29, 12, tzinfo=UTC)
HISTORY = (1.0, 2.0, 3.0, 4.0, 5.0)


def _snap(symbol: str, price: float | None, when: datetime = NOW, change: float | None = 0.5) -> MarketSnapshot:
    return MarketSnapshot(when, symbol, symbol.title(), price, change, "yfinance", history=HISTORY if price else ())


def test_missing_price_is_filled_with_recent_last_good_labeled() -> None:
    stored = {"IPSA": _snap("IPSA", 6800.0, NOW - timedelta(days=3), change=1.2)}

    display, covered = with_last_good_prices([_snap("SP500", 7400.0), _snap("IPSA", None)], stored, NOW)

    ipsa = display[1]
    assert covered == {"IPSA"}
    assert (ipsa.price, ipsa.change_pct, ipsa.history) == (6800.0, None, ())
    assert ipsa.as_of == NOW - timedelta(days=3)
    assert display[0].as_of is None


def test_last_good_older_than_limit_is_not_used() -> None:
    stored = {"IPSA": _snap("IPSA", 6800.0, NOW - timedelta(days=6))}

    display, covered = with_last_good_prices([_snap("IPSA", None)], stored, NOW)

    assert covered == set()
    assert display[0].price is None


def test_symbol_missing_from_run_is_restored_in_expected_order() -> None:
    stored = {"USDPEN": MarketSnapshot(NOW - timedelta(days=1), "USDPEN", "USD/PEN", 3.71, 0.1, "bcentral")}

    display, covered = with_last_good_prices(
        [_snap("USDCOP", 4100.0), _snap("TPM", 4.75)], stored, NOW, ["USDCOP", "USDPEN", "TPM"]
    )

    assert [s.symbol for s in display] == ["USDCOP", "USDPEN", "TPM"]
    assert (display[1].name, display[1].source) == ("USD/PEN", "bcentral")
    assert covered == {"USDPEN"}


def test_labels_in_table_and_text_use_chile_date() -> None:
    # 02:00 UTC del 27-09 es 23:00 del 26-09 en Santiago.
    stored = {"IPSA": _snap("IPSA", 6800.0, datetime(2026, 9, 27, 2, tzinfo=UTC))}
    display, _ = with_last_good_prices([_snap("SP500", 7400.0), _snap("IPSA", None)], stored, NOW)

    assert format_market_line(display[1]) == "Ipsa: 6,800.00 (al 26-09)"
    html = render_assets_table(display)
    assert "al 26-09" in html
    assert html.count("al 26-09") == 1


def test_unavailable_sources_line_rendered_escaped() -> None:
    html = build_email_html("Asunto", "", unavailable_sources=["Investing.com", "USD/PEN", "<x>"])

    assert "Sin datos en esta edicion: Investing.com, USD/PEN, &lt;x&gt;." in html
    assert "Sin datos en esta edicion" not in build_email_html("Asunto", "")


def test_display_names_cover_fx_and_macro() -> None:
    names = market_display_names()

    assert names["USDPEN"] == "USD/PEN"
    assert names["DESEMPLEO"] == "Desempleo Chile"
    assert names["IPSA"] == "IPSA"
