# Siguientes Pasos

Estado a v0.14.0 + cambios sin version (2026-09-29, ver `CHANGELOG.md`
"Unreleased"). Reemplaza la version anterior de este archivo
(escrita en v0.2.0), cuyas opciones A-D quedaron implementadas o superadas.

## Estado de fuentes (medido en vivo el 2026-09-28)

| Fuente | Tipo | Estado |
|--------|------|--------|
| BCCh API | Datos (TPM, IPC, desempleo, USD/PEN) | Funcional (requiere credenciales). Desempleo y USD/PEN agregados el 2026-09-29, **no verificados en vivo** (sin credenciales en la maquina de desarrollo) |
| yfinance 1.7.0 | Datos de mercado + series 1 mes | 17/17 en ~2.5s; IPSA via `MXIPSAGC.SN`; USD/PEN paso al BCCh |
| Federal Reserve | RSS | 20 notas |
| ECB | RSS | 15 notas |
| Financial Times | RSS | 12 notas |
| MarketWatch | RSS | 10 notas |
| Investing.com | RSS | 10 notas (fecha no RFC 822, ya soportada) |
| La Tercera Pulso | RSS oficial + respaldo HTML | 20 notas con fecha real |
| Diario Financiero | RSS de portada filtrado por seccion | 16 de 50 notas (2026-09-29) |

Descarga de RSS: ~2.9s en serie -> ~0.7s en paralelo (0.24s con conexiones
reutilizadas). Detalle en `CHANGELOG.md` (0.14.0).

---

## yfinance y graficos: estado y pendientes

Reparado en 0.14.0 (detalle en `CHANGELOG.md`): una descarga batch de 1 mes
entrega cotizacion + serie; IPSA vuelve via `MXIPSAGC.SN` (velas horarias);
series inconsistentes o vencidas se descartan; version fijada a 1.7.0; y la
tabla de activos del correo muestra una sparkline de 1 mes en HTML/CSS.

### Por que sparklines HTML y no imagenes

Las imagenes embebidas (cid: y base64) ya fallaron en Outlook mobile/web
(`docs/email-output.md`), y Gmail no muestra imagenes `data:`. Las barras con
`border-bottom` en celdas de tabla se ven en todos los clientes, cuestan
~1.3 KB por activo y no agregan dependencias.

### Pendientes

1. ~~USD/PEN~~: resuelto, se toma del BCCh (`F072.PEN.USD.N.O.D`).
   **Verificar en el servidor** con credenciales que la serie venga al dia
   (si el ultimo dato tiene > 7 dias, se oculta y queda un warning).
2. ~~IPSA oficial~~: decidido. La fuente aprobada es `MXIPSAGC.SN` via
   yfinance (2026-09-29; alternativas evaluadas en el README). El BCCh solo
   publica el promedio mensual. Si Yahoo vuelve a cambiar el ticker,
   `python -m scripts.diagnose_market_data` lo muestra como "SIN DATOS".
3. ~~`^TNX`~~: resuelto, el correo muestra el cambio del Treasury 10Y en pb.
4. **Rate limit.** yfinance 1.7 no lanza excepcion por ticker fallido en un
   batch (solo lo registra en su log), asi que el cliente no distingue "sin
   datos" de "bloqueado". Ahora un bloqueo se ve como activos "caida" en la
   salud de fuentes (y avisa a mantenedores), y el correo muestra el ultimo
   precio valido rotulado. Falta cachear la serie (sparkline) buena.
5. **Rol de la IA en "En foco".** Paso (a) implementado: Nix escribe una
   linea de lectura por grafico, sin elegir activos
   (`services/ai/news_chart_readings.py`). Falta probarlo con Ollama real
   (`AI_ENABLED=true`, `AI_DRY_RUN=false`) y revisar el tono de las lineas.
   Paso (b), no implementado: exponer los candidatos como `chart_ids` del writer
   (`asset_trend:COPPER`) para que la IA ordene entre ellos, siempre
   filtrado por los candidatos deterministicos. La IA nunca deberia poder
   pedir un activo que ninguna noticia menciona.
6. **Cobertura de "En foco".** Con las noticias del 2026-09-28, 8 de 78
   notas mencionan un activo; con solo 3 titulares en el correo, algunos
   dias la seccion no aparecera. Falso positivo conocido: "every dollar I
   earn" (finanzas personales) activa DXY; lo mitiga el filtro de calidad de
   titulares.
7. **Graficos IA (PNG).** `services/ai/chart_renderer.py` podria sumar un
   grafico de linea con `MarketSnapshot.history`, pero siguen apagados en el
   correo por decision del MVP. Si se reactivan: `kaleido==0.2.1` con
   `plotly==5.24.1` funcionan; con plotly >= 6 / kaleido >= 1 cambia la API
   (`engine` eliminado) y se necesita Chrome en la imagen Docker.
8. **Telefonos de <= 375 px.** La tabla de activos no cabe (pasaba tambien
   antes de las sparklines). Se podria reducir el padding lateral de las
   secciones o apilar precio y variacion en una sola columna.

---

## Scraping y noticias: siguientes optimizaciones

**2026-10-03:** diagnostico medido de la calificacion de noticias, evaluacion
de Kev (descartado por ahora: requiere GPU) y hoja de ruta por fases en
`docs/news-scoring.md`. Esa hoja de ruta reemplaza a los puntos 4 y 5 de
esta lista como plan de trabajo.

1. ~~Ampliar fuentes chilenas~~: Diario Financiero agregado (RSS de portada,
   filtrado por seccion).
2. **GET condicional.** Guardar `ETag`/`Last-Modified` por feed y enviar
   `If-None-Match`/`If-Modified-Since` en el monitor de alto impacto (corre
   cada 15 min) para no bajar feeds sin cambios.
3. **Monitor mas liviano.** `run_high_impact_monitor_once` llama a
   `collect_market_and_news`, que pide los 18 tickers y el BCCh en cada
   corrida (96 veces al dia, tambien de noche y fines de semana). Podria
   reutilizar el ultimo snapshot o limitarse al horario de mercado.
4. ~~Falsos positivos del clasificador~~: resuelto con limites de palabra y
   tests de regresion. Region por defecto "Chile" para medios chilenos,
   cupo chileno en titulares y filtro de comunicados administrativos de
   bancos centrales: hechos (ver CHANGELOG). Queda abierto:
   `HIGH_SIGNAL_TERMS` y `LOW_VALUE_PATTERNS` (`services/news_quality.py`)
   siguen buscando por substring e incluyen el nombre de la fuente en el
   texto evaluado ("federal reserve" siempre es alta senal); e
   `impact_scoring` suma +1 a Latam/EE.UU./Global pero no a Chile.
5. **Deduplicacion.** Sigue siendo O(n^2) con `SequenceMatcher`; el cache
   `lru_cache(maxsize=512)` es chico para ~100 notas (~5.000 pares). Con el
   filtro de recencia antes de deduplicar el volumen bajo, pero puede
   mejorarse con un indice por tokens.
6. ~~BCCh~~: resuelto (cliente por request, series en paralelo, logs con
   el mensaje sin credenciales).

---

## Paquetes: estado tras la limpieza

| Paquete | Uso real | Accion |
|---------|----------|--------|
| `cachetools` | Nunca importado | Eliminado en 0.14.0 |
| `pytest`, `ruff` | Solo desarrollo | Movidos a `requirements-dev.txt` / extra `dev` (fuera de la imagen Docker) |
| `plotly`, `kaleido` | Solo render PNG IA (dormido en el correo MVP) | Mantener mientras exista el render IA; las sparklines no los usan |
| `pandas` | Import directo solo en tests | Mantener: dependencia de yfinance |
| `python-dotenv` | No importado | Mantener: `pydantic-settings` lo usa para leer `.env` |
| `lxml` | Parser de BeautifulSoup | Mantener (respaldo HTML de La Tercera) |
| `curl_cffi` | Sesion de yfinance | Quitado de requirements: lo instala yfinance >= 1.0 |

Otros restos: los settings `app_env` y `ai_chart_output_dir` no se leen en
ningun lado. Los pins `lxml==5.3.0` y `pydantic==2.9.2` no compilan en
Python 3.14 (Docker usa 3.11, asi que produccion no se ve afectada, pero si
un entorno local nuevo).

## Correo y datos: hallazgos del 2026-09-29

1. ~~Brent -8.46%~~: resuelto. Era el cambio de contrato de `BZ=F`; los
   futuros `=F` usan ahora el contrato vigente (`underlyingSymbol`).
2. **Router de temas IA**: respuesta vacia intermitente para una region
   (`Strict JSON parse failed ... char 0`); el pipeline continua sin ella.
3. ~~Correo en telefonos y clientes reales~~: resuelto con el diseno
   Editorial (columnas fluidas, solo claro, logo embebido); el usuario lo
   valido en Outlook el 2026-09-29.
4. ~~**Nix**: codigos y prefijos rotos~~: resuelto el 2026-09-30 con una
   limpieza deterministica (`services/ai/editorial_polish.py`) y reglas en
   los prompts. Queda por revisar en correos reales el texto en ingles.

## Siguiente mision: auditoria de seguridad

Superficie publica nueva (servicio de suscripcion via Funnel) y datos
personales en MySQL. Alcance detallado en `docs/HANDOFF.md` ("Siguiente
mision"): servicio publico, datos y respaldos, secretos (rotar la clave del
BCCh), servidor `nixbox`, politica de Tailscale, dependencias y correo.
Despues: frontend de las paginas de suscripcion con logo (CSP hoy bloquea
imagenes).

## Mailing con suscripcion (MySQL): implementado, falta activarlo

Implementado el 2026-09-30 y apagado por defecto (ver README "Mailing con
suscripcion" y DEPLOY.md para activarlo). Decision del usuario: servicio web
propio publicado con Tailscale Funnel (no Google/Microsoft Forms), para tener
doble confirmacion y baja de un clic.

Pendientes:

1. **Encender el envio** (DEPLOY.md, paso 5), despues de la auditoria.
   Pasos 1-3 hechos el 2026-09-30 (`.env`, contenedores, Funnel en 8090) y
   links probados desde PC y celulares. Falta `subscribers add dmac@udd.cl`
   y `MAILING_ENABLED=true`.
2. ~~DDL de MySQL no probado en vivo~~: verificado el 2026-09-30 en nixbox
   con un MySQL 8.4 desechable y la imagen desplegada (esquema idempotente,
   alta/confirmacion/baja/borrado, token sensible a mayusculas, duplicados).
3. **SMTP institucional de la UDD** antes de ~200 suscriptores (Gmail
   personal ~500 destinatarios/dia; cada suscriptor recibe 2 correos).
4. **Difusion**: la URL de Funnel (`nixbox.<tailnet>.ts.net`) expone el
   nombre del tailnet; un dominio propio del club seria mas presentable
   (`dmac.cl` libre el 2026-09-30; Cloudflare DNS + Tunnel como opcion).
5. **Politica de privacidad**: el formulario muestra finalidad y contacto
   (`OPS_EMAIL_TO`); falta revisarla con el club (ley 19.628 / 21.719).
6. **Opcional**: aviso a mantenedores con altas/bajas del dia; limpiar filas
   `pending` vencidas (> 30 dias); elegir edicion (manana, cierre o ambas)
   si las bajas lo justifican (hoy: ambas siempre, decision del club).
7. **Difusion**: link de `MAILING_PUBLIC_URL` en Instagram/Linktree del club,
   QR en afiches y charlas, firma de correo de la directiva.

## CI/CD

- Hecho: GitHub Actions (`.github/workflows/ci.yml`) corre `ruff check` y
  `pytest` con Python 3.11 en cada push y PR. Se activa con el primer push
  que incluya el archivo.
- Pendiente: proteger `main` en GitHub para exigir CI verde antes del merge.

---

## Salud de fuentes: estado y pendientes

Implementado (ver `CHANGELOG.md`, "Unreleased"): chequeo por corrida,
histeresis de dos corridas, tablas `source_health`/`source_state`, comando
`python -m app.main health`, aviso a `OPS_EMAIL_TO`, ultimo dato valido
rotulado "al DD-MM" y linea "Sin datos en esta edicion" en el correo.

1. **Configurar `OPS_EMAIL_TO`** en el `.env` del servidor (vacio = solo log).
2. **Calibrar umbrales** tras un par de semanas mirando `health`: frescura
   por feed (`NEWS_FRESHNESS_HOURS`) y salto maximo de precio (25%).
3. **Fines de semana.** El monitor (si esta activo) corre tambien de noche y
   fines de semana; un feed que no publica el domingo podria quedar
   "degradada" el lunes temprano. Si pasa, sumar el feed al diccionario de
   frescura o evaluar solo en dias habiles.
4. **Errores reales por fuente.** Hoy la salud se deduce de lo que llego (0
   notas = caida); el mensaje de error queda en el log. Si hace falta, los
   clientes podrian reportar el error a la salud directamente.
5. **Resumen semanal** opcional a mantenedores aunque no haya cambios.
