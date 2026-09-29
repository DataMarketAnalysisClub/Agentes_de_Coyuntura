"""Diagnostico standalone de la fuente de datos de mercado (yfinance).

Uso (desde la raiz del proyecto, con el venv activado):

    .venv/bin/python -m scripts.diagnose_market_data

Corre cada ticker por separado, capturando el error real (no solo el tipo),
e imprime un resumen. Util para reportar el problema real cuando "yfinance
no funciona" en el servidor: pegar la salida completa en el chat/issue.

No modifica nada del pipeline productivo; es de solo lectura.
"""

from __future__ import annotations

import sys
import traceback

from data_sources.yfinance_client import DEFAULT_ASSETS, YFinanceClient


def main() -> int:
    import curl_cffi
    import yfinance

    print(f"yfinance version: {getattr(yfinance, '__version__', 'desconocida')}")
    print(f"curl_cffi version: {getattr(curl_cffi, '__version__', 'desconocida')}")
    print(f"python: {sys.version}")
    print("-" * 72)

    client = YFinanceClient(max_retries_per_ticker=1)
    ok = 0
    failed: list[str] = []

    for asset in DEFAULT_ASSETS:
        try:
            quote = client._fetch_one(asset)  # noqa: SLF001 - diagnostico intencional
        except Exception:  # noqa: BLE001
            print(f"[EXCEPCION NO CAPTURADA] {asset.symbol} ({asset.yf_ticker})")
            traceback.print_exc()
            failed.append(asset.symbol)
            continue

        if quote.price is None:
            print(
                f"[SIN DATOS] {asset.symbol:12s} ticker={asset.yf_ticker:12s} "
                f"interval={asset.interval} -> price=None"
            )
            failed.append(asset.symbol)
        else:
            print(
                f"[OK]        {asset.symbol:12s} ticker={asset.yf_ticker:12s} "
                f"-> price={quote.price:.4f} change_pct={quote.change_pct} "
                f"historia={len(quote.history)} cierres"
            )
            ok += 1

    print("-" * 72)
    print(f"OK: {ok}/{len(DEFAULT_ASSETS)}")
    if failed:
        print(f"Sin datos o con error: {', '.join(failed)}")
        print(
            "\nRevisa los logs de arriba (nivel WARNING de "
            "data_sources.yfinance_client) para el mensaje de error real "
            "de cada ticker fallido -- ahora incluye el texto de la "
            "excepcion, no solo el tipo."
        )
    return 0 if not failed else 1


if __name__ == "__main__":
    import logging

    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    raise SystemExit(main())
