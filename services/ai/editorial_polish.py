"""Limpieza deterministica del texto que escribe Nix.

El modelo recibe los codigos internos de los activos ("USDCLP", "US10Y") en
los snapshots y en `affected_assets`, y a veces los copia al titular, que
termina en el asunto del correo. Tambien abre frases con prefijos rotos
("Posible que...", "Preliminar que..."). El prompt pide lo contrario, pero
esta capa lo corrige aunque el modelo no obedezca.

Solo reemplaza codigos en MAYUSCULAS y con limites de palabra: "Oro" o
"el oro" no se tocan; "GOLD" si.
"""

from __future__ import annotations

import re

# Codigo interno -> nombre legible en una frase en espanol. Los codigos que ya
# se leen bien (IPSA, DXY, VOO, WTI, UF, TPM, IPC, IMACEC) no estan.
ASSET_CODE_NAMES: dict[str, str] = {
    "USDCLP": "USD/CLP",
    "USDPEN": "USD/PEN",
    "USDBRL": "USD/BRL",
    "USDMXN": "USD/MXN",
    "USDCOP": "USD/COP",
    "DOLAR_OBS": "dólar observado",
    "COPPER": "cobre",
    "COBRE_BML": "cobre BML",
    "GOLD": "oro",
    "BRENT": "Brent",
    "SP500": "S&P 500",
    "NASDAQ100": "Nasdaq 100",
    "EUROSTOXX50": "EuroStoxx 50",
    "BOVESPA": "Bovespa",
    "MEXIPC": "IPC de México",
    "DESEMPLEO": "desempleo",
}

_CODE_RE = re.compile(r"(?<![\w/])(" + "|".join(sorted(map(re.escape, ASSET_CODE_NAMES), key=len, reverse=True))
                      + r")(?![\w/])")
# US10Y, US30Y, UST2Y -> "Treasury 10 años"
_TREASURY_RE = re.compile(r"(?<![\w/])UST?(\d{1,2})Y(?![\w/])")

# Prefijos de cautela sin verbo al inicio de una frase.
_HEDGE_RE = re.compile(
    r"(^|[.!?]\s+)(?:Posible|Posiblemente|Preliminar|Preliminarmente|Probable)\s+que\b",
)
_HEDGE_REPLACEMENTS = {"probable": "Es probable que"}

_SENTENCE_START_RE = re.compile(r"(^|[.!?:]\s+)$")


def _at_sentence_start(text: str, index: int) -> bool:
    return bool(_SENTENCE_START_RE.search(text[:index]))


def _readable_code(text: str, match: re.Match, name: str) -> str:
    if _at_sentence_start(text, match.start()):
        return name[:1].upper() + name[1:]
    return name


def replace_asset_codes(text: str) -> str:
    text = _CODE_RE.sub(lambda m: _readable_code(m.string, m, ASSET_CODE_NAMES[m.group(1)]), text)
    return _TREASURY_RE.sub(lambda m: f"Treasury {int(m.group(1))} años", text)


def fix_hedge_prefixes(text: str) -> str:
    def repl(match: re.Match) -> str:
        word = match.group(0)[len(match.group(1)):].split()[0].lower()
        return match.group(1) + _HEDGE_REPLACEMENTS.get(word, "Es posible que")

    return _HEDGE_RE.sub(repl, text)


def polish_text(text: str) -> str:
    if not text:
        return text
    return fix_hedge_prefixes(replace_asset_codes(text))


def polish_editorial(email):
    """Aplica `polish_text` a todo el texto visible de un AiEditorialEmail."""
    email.subject = polish_text(email.subject)
    email.preheader = polish_text(email.preheader)
    email.headline = polish_text(email.headline)
    for field in ("executive_summary", "market_context", "risk_flags", "editorial_cautions"):
        setattr(email, field, [polish_text(item) for item in getattr(email, field)])
    for section in email.sections:
        section.body = [polish_text(item) for item in section.body]
        section.bullets = [polish_text(item) for item in section.bullets]
        section.cautions = [polish_text(item) for item in section.cautions]
    return email
