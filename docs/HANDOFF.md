# Handoff: sesion 2026-09-29

Estado para retomar el trabajo en otra sesion. Rama
`feat/v0.14-market-data-news-charts`. Todo esta commiteado localmente
(sesiones 2026-09-28 y 2026-09-29), **sin push**: el push lo hace el
usuario; Claude tiene prohibido hacer push. Detalle en
`CHANGELOG.md` (entradas "Unreleased" y 0.14.0) y pendientes en
`NEXT_STEPS.md`.

## Sesion 2026-09-28 (resumen)

Outlook desktop, retiro de Google Finance y stubs muertos, scraping en
paralelo, yfinance 1.7.0 reparado con sparklines de 1 mes, y la seccion
"En foco" (graficos elegidos por los titulares). Ver 0.14.0 en el changelog.

## Sesion 2026-09-29: que se hizo

Decisiones del usuario: implementar la lectura de Nix por grafico (paso a),
sacar USD/PEN del BCCh y sumar la tasa de desempleo, y agregar el RSS de DF.

1. **Clasificador con limites de palabra** (`services/news_classifier.py`):
   plural opcional, prefijos explicitos (`geopolit*`), excepcion para el IPC
   de Mexico y "US" en mayusculas (no "US$") como EE.UU.
2. **Diario Financiero** en `ChileNewsClient`: RSS de portada filtrado por
   seccion de la URL; las fuentes chilenas corren en paralelo.
3. **BCCh**: desempleo (`F049.DES.TAS.INE9.10.M`) y USD/PEN
   (`F072.PEN.USD.N.O.D`, con historia de 1 mes). USD/PEN salio de
   `DEFAULT_ASSETS` de yfinance. El cliente ya no filtra `NaN`
   erroneamente, no deja clientes HTTP abiertos, pide en paralelo y nunca
   loguea credenciales.
4. **Lectura de Nix en "En foco"** (`services/ai/news_chart_readings.py`,
   prompt `prompts/ai/news_chart_reading.md`): una llamada chica a la IA
   por correo, solo con los graficos ya elegidos; se valida simbolo,
   largo y lenguaje de recomendacion. Los jobs pasan `news_charts` a
   `build_email_html`.

## Decisiones tomadas (no re-discutir sin motivo)

- Las de la sesion anterior siguen vigentes (seleccion deterministica,
  graficos HTML/CSS, sin reintento por ticker ante batch vacio, "dolar" vs
  "dollar").
- DF: solo titulo, bajada y link del RSS; Opinion queda fuera (es
  interpretacion, no hechos).
- La lectura de Nix va rotulada "Lectura de Nix (IA)" para separar
  interpretacion de datos.

## Verificacion

- 286 tests pasan en Python 3.11 con los pins; `ruff check .` limpio.
- Morning brief local (sin correo, sin credenciales BCCh, IA apagada):
  73 KB, "En foco" presente.
- **No verificado en vivo**: series BCCh nuevas (no hay credenciales en la
  maquina de desarrollo) y la lectura de Nix con Ollama real.
- Entorno: `.venv` (ignorado por git) creado con
  `mise exec python@3.11 -- python -m venv .venv && .venv/bin/pip install -r requirements.txt`.

## Proximos pasos sugeridos

1. En el servidor: `pip install -r requirements.txt`,
   `python -m scripts.diagnose_market_data` (esperado: OK 17/17) y una
   corrida con credenciales BCCh para ver USD/PEN y Desempleo en la tabla.
2. Probar la lectura de Nix con `AI_ENABLED=true AI_DRY_RUN=false`.
3. Integrar la rama (merge a `main` y push: los hace el usuario).
4. Resto en `NEXT_STEPS.md`: IPSA oficial, `^TNX` en pb, GET condicional,
   monitor mas liviano, region por fuente para notas chilenas, extra `dev`.
