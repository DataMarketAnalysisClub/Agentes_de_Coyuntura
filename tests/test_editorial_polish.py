from unittest.mock import patch

import pytest
from test_ai_editorial_writer import _make_report as make_report
from test_ai_editorial_writer import _make_settings as make_settings
from test_ai_editorial_writer import _make_snapshots as make_snapshots

from services.ai.editorial_polish import fix_hedge_prefixes, polish_text, replace_asset_codes
from services.ai.editorial_writer import run_editorial_writer


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("USDCLP sube por el cobre", "USD/CLP sube por el cobre"),
        ("El USDCLP y el COPPER caen", "El USD/CLP y el cobre caen"),
        ("COPPER lidera el día", "Cobre lidera el día"),
        ("Fed presiona al US30Y y al US10Y", "Fed presiona al Treasury 30 años y al Treasury 10 años"),
        ("UST2Y en máximos", "Treasury 2 años en máximos"),
        ("SP500 y NASDAQ100 al alza", "S&P 500 y Nasdaq 100 al alza"),
        ("Dólar sube. DOLAR_OBS en alza", "Dólar sube. Dólar observado en alza"),
    ],
)
def test_asset_codes_become_readable_names(raw, expected) -> None:
    assert replace_asset_codes(raw) == expected


@pytest.mark.parametrize(
    "text",
    [
        "El oro y el cobre suben",           # nombres ya legibles
        "USD/CLP sube",                        # formato legible con barra
        "IPSA, DXY, WTI, UF y TPM",            # codigos que se leen bien
        "Goldman Sachs y Copperfield",         # palabras que contienen un codigo
        "gold y copper en minusculas",         # solo MAYUSCULAS
        "Brent y Bovespa",                     # ya en forma de nombre
        "El ticker USDCLPX no existe",         # sin limite de palabra
        "Dato del 10Y",                        # sin prefijo US
    ],
)
def test_readable_text_is_left_alone(text) -> None:
    assert replace_asset_codes(text) == text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Posible que el cobre siga al alza.", "Es posible que el cobre siga al alza."),
        ("Preliminar que la Fed recorte.", "Es posible que la Fed recorte."),
        ("Probable que el dólar ceda.", "Es probable que el dólar ceda."),
        ("El IPC subió. Posiblemente que siga.", "El IPC subió. Es posible que siga."),
        ("Es posible que el cobre suba.", "Es posible que el cobre suba."),
        ("Resulta posible que el cobre suba.", "Resulta posible que el cobre suba."),
    ],
)
def test_hedge_prefixes_get_a_verb(raw, expected) -> None:
    assert fix_hedge_prefixes(raw) == expected


def test_polish_text_handles_empty() -> None:
    assert polish_text("") == ""


def test_writer_output_is_polished_before_reaching_subject_and_body() -> None:
    settings = make_settings()
    raw = (
        '{"status":"ok","generated_at":"2026-09-30T12:00:00Z",'
        '"subject":"USDCLP y COPPER","preheader":"US10Y al alza",'
        '"headline":"USDCLP sube con el COPPER","executive_summary":["Posible que el US30Y siga"],'
        '"market_context":["SP500 estable"],'
        '"sections":[{"heading":"Chile","body":["El USDCLP sube"],"bullets":["COPPER cae"],'
        '"cautions":["Preliminar que siga"]}],'
        '"risk_flags":["GOLD en máximos"],'
        '"chart_specs":[],"source_notes":[],"editorial_cautions":["USDCLP volátil"]}'
    )
    with patch("services.ai.editorial_writer.OllamaCloudClient") as mock_client_class:
        mock_client = mock_client_class.return_value
        mock_client.settings = settings
        mock_client.is_enabled.return_value = True
        mock_client.is_dry_run.return_value = True
        mock_client.chat_json.return_value = raw
        result = run_editorial_writer(make_report(), make_snapshots())

    email = result.response
    assert email.headline == "USD/CLP sube con el cobre"
    assert email.subject == "USD/CLP y cobre"
    assert email.preheader == "Treasury 10 años al alza"
    assert email.executive_summary == ["Es posible que el Treasury 30 años siga"]
    assert email.market_context == ["S&P 500 estable"]
    assert email.sections[0].body == ["El USD/CLP sube"]
    assert email.sections[0].bullets == ["Cobre cae"]
    assert email.sections[0].cautions == ["Es posible que siga"]
    assert email.risk_flags == ["Oro en máximos"]
    assert email.editorial_cautions == ["USD/CLP volátil"]
