# Changelog

## [Unreleased] - 2026-09-29

### Cambiado (asunto con el titular)
- El asunto lleva el titular de Nix: "DMAC Brief · 29 sep — <titular>" (y
  "DMAC Cierre · ..." en el cierre), recortado a 80 caracteres. Sin IA se
  mantiene el asunto fijo. La fecha larga de la cabecera ya no se lee del
  asunto: los jobs pasan `edition_date`.

### Corregido (modo oscuro, logo y presentacion en la bandeja)
- Se retira la paleta oscura propia: Outlook nuevo la aplicaba segun el tema
  de Windows aunque el lector eligiera "fondo claro", y ademas convertia los
  colores (fondo gris translucido, logo invisible). El correo es solo claro,
  con tarjeta blanca pura y texto casi negro, que los clientes invierten bien.
- Logo embebido como parte `multipart/related` (`cid:dmac-logo`), con el
  fondo blanco dentro del PNG (`assets/Dmac_logo_email.png`): se ve aunque
  Outlook bloquee imagenes externas y no se oscurece en modo oscuro.
- Remitente con nombre visible (`EMAIL_FROM_NAME`, "DMAC Brief · Nix") y
  vista previa oculta con el titular de Nix, para que la bandeja no muestre
  "PRUEBA · DATA MARKET ANALYSIS CLUB UDD".
- Textos chicos de 11/12 px suben a 12/13 px; la fuente y el periodo de cada
  activo van en su propia linea bajo el nombre (se cortaban en telefonos).

### Agregado (series del Banco Central)
- Dolar observado, UF y cobre BML como series diarias del BCCh con ~1 mes
  de historia, junto a los precios de Yahoo (no los reemplazan).
- IPC 12 meses e IMACEC 12 meses. TPM, IPC mensual, IPC 12 meses, IMACEC y
  desempleo muestran su periodo ("ago-26", "29-09") y el cambio en puntos
  porcentuales contra el dato anterior, en color neutro. Nuevo
  `BCentralClient.fetch_indicator` (valor, fecha y valor anterior).
- Codigos verificados con `SearchSeries` y documentados en el README. El IPSA
  del BCCh es solo mensual: el diario sigue viniendo de Yahoo.

### Corregido (tests)
- Los tests ya no leen el `.env` local: con credenciales reales, `Settings()`
  las tomaba y un assert fallido podia imprimir la contrasena del BCCh.

### Cambiado (diseno "Editorial" del correo)
- Nuevo look elegido en Claude Design (propuesta A): fondo marfil, titulares
  en Georgia, cabecera tipo periodico con logo, fecha larga en espanol y
  edicion ("Edicion de la manana/de cierre"); lineas finas entre secciones.
- Orden: "Lo esencial" (Nix, con titular y resumen numerado; Chile antes que
  Global), cifras clave (USD/CLP, Cobre, IPSA, TPM), sentimiento en una
  linea, titulares, mercados agrupados (Chile, EE.UU., materias primas,
  resto del mundo) y "En foco" en dos columnas.
- Responsivo sin depender de `@media`: las grillas son columnas
  `inline-block` que se apilan solas (2x2 y 1 columna en telefonos), con
  tabla condicional `<!--[if mso]>` para Outlook de escritorio. Verificado en
  1200, 390 y 320 px sin scroll horizontal; 55 KB.
- Numeros en formato chileno (970,93 · 11.133), Treasury 10Y con variacion
  en puntos base, TPM/IPC/desempleo en % sin "s/d", tildes en todo el texto
  fijo y en los nombres de activos; el IPC del BCCh se rotula "IPC mensual".
- Se quitan el grafico "Titulares por region" y el simbolo repetido bajo
  cada activo ("IPSA / IPSA"). Las viñetas de las secciones de Nix solo se
  muestran si la seccion no trae parrafos (repetian el titular en ingles).
- El HTML de Nix, antes duplicado en los dos jobs, vive en
  `render_nix_editorial` (`services/email_formatter.py`).

### Corregido (cambio de contrato en futuros)
- Los futuros continuos de Yahoo (`BZ=F`, `CL=F`, cobre, `GC=F`) empalman
  el contrato siguiente sin ajustar al vencer el vigente: el 29-09 el Brent
  mostro -8,09% (nov 105,28 -> dic 96,84) cuando el contrato de diciembre
  cayo ~1%, y Nix interpreto esa caida. El cliente ahora resuelve el
  contrato vigente (`underlyingSymbol`, ej. `BZZ26.NYM`) y calcula precio,
  variacion e historia del mes sobre ese solo contrato. Si Yahoo no responde,
  usa el continuo como antes y registra un warning.

### Corregido (correo multiplataforma)
- Logo roto en Gmail y Outlook web/nuevo: ahora se referencia por HTTPS
  (`EMAIL_LOGO_URL`) en vez de `data:` URI, sobre un recuadro blanco (el PNG
  es oscuro y se perdia en el azul del header), con texto alternativo "DMAC".
  El correo baja ~26 KB (72 -> 47 KB).
- Scroll horizontal en telefonos: la tabla de activos fijaba un ancho minimo
  de ~436 px. Padding 8 px, sparkline de 48 px, precios >= 10.000 sin
  decimales y "yfinance" en una nota al pie (solo se repite la fuente cuando
  es otra). Sin scroll desde ~340 px; media query para margenes en <= 480 px.
- `rgba()` reemplazado por hex en el header y el bloque de Nix (Outlook de
  escritorio lo ignora); subtitulo del header con mas contraste.

### Cambiado (relevancia para el lector chileno)
- Cupo chileno en los titulares principales (`select_executive_news`,
  `guaranteed_region="Chile"`): si ninguno de los 3 es de Chile y hay una
  nota chilena que pasa el filtro de calidad, la mejor reemplaza al ultimo.
  Nunca se fuerza una nota que no pase calidad.
- Region por defecto "Chile" para La Tercera Pulso y Diario Financiero
  cuando ninguna palabra clave indica otra region (salvo la seccion
  Internacional de DF). Con las noticias del 2026-09-29: 7 -> 30 de 36 notas
  chilenas quedan como Chile.
- Se descartan comunicados administrativos de la Fed y el BCE (aprobaciones
  de solicitudes bancarias, enforcement actions, consultas publicas,
  billetes): antes pasaban siempre y desplazaban noticias de mercado.

### Corregido (relevancia)
- Diario Financiero no tenia tier en `SOURCE_TIERS` (quedaba en el mas bajo);
  ahora es tier 2, igual que La Tercera Pulso.

### Agregado (salud de fuentes)
- `services/source_health.py`: evalua cada corrida contra lo esperado. Un
  feed sin notas o un activo sin precio queda "caida"; un feed cuya nota mas
  reciente supera su umbral (48 h; 7 dias para Fed y BCE) o un precio que
  salta mas de 25% contra el ultimo guardado queda "degradada". Con
  histeresis: dos corridas malas seguidas para cambiar de estado, una buena
  para volver a ok.
- Tablas `source_health` (por corrida, 30 dias de retencion) y
  `source_state` (estado vigente). Comando `python -m app.main health`.
- Aviso a mantenedores (`OPS_EMAIL_TO`, vacio = solo log): un correo por
  corrida con cambios de estado. `EmailSender.send` acepta `recipients`
  para que estos avisos nunca lleguen a la lista del club.
- Correo: si un activo no trae precio hoy, se muestra su ultimo dato valido
  (hasta 5 dias) rotulado "al DD-MM", sin variacion ni sparkline. Solo para
  mostrar: la IA, el sentimiento y el puntaje de impacto usan los datos de
  hoy, y el respaldo no se persiste. Una linea discreta lista las fuentes
  sin datos en la edicion.
- CI en GitHub Actions (`.github/workflows/ci.yml`): `ruff check` y
  `pytest` con Python 3.11 en cada push y PR.

### Cambiado (paquetes)
- `pytest` y `ruff` pasan a `requirements-dev.txt` (y al extra `dev` de
  `pyproject.toml`): la imagen Docker ya no los instala.

### Agregado
- Diario Financiero como segunda fuente chilena (`ChileNewsClient._fetch_df`):
  RSS de portada filtrado por seccion (Mercados, Economia y Politica,
  Empresas, Internacional, Primer Click). Las fuentes chilenas se descargan
  en paralelo con un circuit breaker por medio.
- BCCh: tasa de desempleo (`F049.DES.TAS.INE9.10.M`, fila "Desempleo Chile")
  y USD/PEN (`F072.PEN.USD.N.O.D`) con variacion diaria y ~1 mes de historia
  (sparkline y "En foco"). Settings `BCENTRAL_UNEMPLOYMENT_SERIES` y
  `BCENTRAL_USDPEN_SERIES`.
- "En foco": linea "Lectura de Nix (IA)" por grafico
  (`services/ai/news_chart_readings.py`). La seleccion sigue siendo
  deterministica; la IA solo redacta sobre los candidatos y se descartan
  lecturas fuera de ellos, demasiado largas o con lenguaje de recomendacion.
  `build_email_html` acepta `news_charts` ya seleccionados.

### Cambiado
- USD/PEN sale de yfinance (`PEN=X` traia velas inconsistentes) y se toma
  del BCCh.
- `BCentralClient`: ya no crea un `httpx.Client` que nunca se cerraba; las
  series se piden en paralelo entre si y con yfinance; los logs incluyen el
  mensaje de error sin credenciales (un error HTTP de httpx trae la URL con
  usuario y contrasena) y la descripcion de los codigos de error de la API.
- `services/news_classifier.py`: palabras clave con limites de palabra y
  plural opcional. Corrige falsos positivos por substring (`"us "` en
  focus/bonus, `"sec"` en sector, `"oil"` en turmoil, `"rate"` en corporate,
  `"oro"` en deterioro, `"war"` en warned, `"fiscal"` en fiscalizacion) y el
  IPC de Mexico ya no se clasifica como Chile. "US" en mayusculas sigue
  contando como EE.UU. (no "US$").

### Corregido
- BCCh: los dias sin dato (`"NaN"`) se tomaban como observaciones validas
  (`float("NaN")` no falla), por lo que el "ultimo valor" podia ser NaN.

## [0.14.0] - 2026-09-22

Primera pasada de fixes tras varios meses de marcha blanca en servidor propio.

### Eliminado
- Google Finance se retira por completo del pipeline (decision del club):
  se borran `data_sources/google_finance_client.py` y
  `tests/test_google_finance_client.py`.
  - `services/market_sentiment.py`: `build_market_sentiment` ya no recibe
    `google_items`; el sentimiento de mercado se calcula solo con snapshots
    de yfinance/BCCh.
  - `services/market_snapshot.py`: el fallback de mercado ya no usa
    `GoogleFinanceQuoteClient`; por ahora cae a `NoopMarketClient` (sin
    proveedor de respaldo). yfinance pasa a ser la unica fuente de precios.
- Codigo y paquetes muertos:
  - `data_sources/alpha_vantage_client.py`, `data_sources/fred_client.py` y
    `data_sources/economic_calendar_client.py` (placeholders nunca importados).
  - Settings `FRED_API_KEY` y `ALPHA_VANTAGE_API_KEY` (solo los usaban esos
    placeholders) y sus entradas en `.env.example`/`.env.production.example`.
    Un `.env` existente que las tenga sigue funcionando (`extra="ignore"`).
  - Dependencia `cachetools` (declarada, nunca importada).

### Cambiado (yfinance mas resiliente)
- `data_sources/yfinance_client.py`:
  - Los logs de error ahora incluyen el mensaje real de la excepcion
    (`str(exc)`), no solo el tipo. Antes era imposible diagnosticar a
    distancia por que fallaba (429, JSON invalido, timeout, etc.).
  - Soporte opcional a `curl_cffi` (impersonation de navegador) via sesion
    inyectada a `yf.download`, mitigacion recomendada por el propio proyecto
    yfinance para el bloqueo anti-bot de Yahoo. Si `curl_cffi` no esta
    instalado, sigue funcionando igual que antes.
  - Reintento con backoff (`max_retries_per_ticker`, default 2) en el
    fallback ticker-por-ticker.
  - `requirements.txt`/`pyproject.toml`: se relaja el pin de `yfinance==0.2.48`
    (desactualizado, Yahoo cambio su API varias veces desde entonces) a
    `yfinance>=0.2.48`; se agrega `curl_cffi` como dependencia.
- `scripts/diagnose_market_data.py` (NUEVO): script standalone para correr en
  el servidor y ver, ticker por ticker, cual falla y con que error real.

### Correo: fixes de renderizado en clientes de escritorio
- `services/email_formatter.py`:
  - Se agrega `font-family: Arial, Helvetica, sans-serif` explicito (body,
    tablas contenedoras y `<style>` en el head). No existia en ningun lado
    del archivo, por lo que Outlook de escritorio caia al serif por defecto
    (Times New Roman) en vez de la tipografia de marca.
  - El header y la card "Analisis de Nix" usan `background: linear-gradient`
    que Outlook de escritorio ignora sin fallback, dejando texto blanco
    sobre fondo blanco/transparente (invisible). Se agrega `bgcolor` (atributo
    HTML) como color solido de respaldo.
  - `render_market_sentiment_section`: la fila "label vs score" usaba
    `display: flex`, no soportado por el motor Word de Outlook de escritorio.
    Se reemplaza por una tabla `role="presentation"` con dos celdas.

### Rendimiento
- `jobs/common.py`: `collect_market_and_news` corria mercado (yfinance +
  BCCh), RSS y scraping de Chile en serie. Ahora corren en paralelo
  (`ThreadPoolExecutor`, 3 llamadas HTTP independientes), acotando el tiempo
  total a la fuente mas lenta en vez de la suma de las tres.

### yfinance reparado + sparklines de 1 mes en el correo
- `data_sources/yfinance_client.py`:
  - Una sola descarga batch de 1 mes (`period="1mo"`) por intervalo, de la
    que salen la cotizacion (ultimo cierre, variacion diaria) y la serie para
    graficos (`Quote.history`, hasta 22 cierres). Medido: 18 activos en
    ~2.5s (antes ~6.2s con `period="5d"`).
  - IPSA: `^IPSA` ya no existe en Yahoo. Se usa `MXIPSAGC.SN` (Bolsa de
    Santiago), que coincide con el nivel del S&P IPSA (11.137,23, -1,06% el
    2026-09-28, igual a lo reportado por la prensa). Su historial diario en
    Yahoo trae 1 dato, asi que se piden velas horarias (`interval="1h"`) y se
    toma el ultimo cierre de cada dia. El IPSA vuelve a la tabla y al
    sentimiento de mercado.
  - Validacion antes de publicar: se descartan velas con cierre fuera de
    [minimo, maximo]; si son mas del 25% se descarta la serie completa
    (`PEN=X`: 16 de 23 velas inconsistentes, ahora "s/d" en vez de un precio
    erroneo). Series con ultimo cierre de hace mas de 7 dias se descartan.
  - Se deja de inyectar una sesion `curl_cffi` propia: yfinance >= 1.0 crea
    la suya con impersonation de Chrome y pide no reemplazarla. Se activan
    sus reintentos nativos para errores transitorios de red.
  - Batch vacio ya no dispara el reintento ticker por ticker (hasta 36
    requests extra justo cuando Yahoo limita); solo se reintenta por ticker
    si el batch lanza una excepcion. Vuelve a pasar
    `test_yfinance_client_does_not_retry_every_symbol_when_batch_is_empty`.
- `requirements.txt`/`pyproject.toml`: `yfinance==1.7.0` (probada en vivo y
  con los pins en Python 3.11); se quita `curl_cffi` explicito (lo instala
  yfinance).
- `storage/models.py`: `MarketSnapshot.history` (solo en memoria, no se
  guarda en SQLite); `services/market_snapshot.py` lo propaga.
- `services/email_charts.py`: `render_sparkline` y columna "1 mes" en la
  tabla de activos (HTML/CSS sin imagenes; ver `docs/email-output.md`). La
  fuente pasa a la linea secundaria del activo para no sumar una quinta
  columna.
- `scripts/diagnose_market_data.py`: informa version de curl_cffi, intervalo
  y cantidad de cierres por ticker.

### Graficos guiados por noticias ("En foco")
- Nuevo concepto de graficos del correo: se eligen segun los titulares
  publicados. Si una noticia habla de cobre y del peso chileno, aparecen los
  graficos de 1 mes del Cobre y del USD/CLP, citando el titular que los
  activo.
- `services/news_charts.py` (NUEVO): `assets_mentioned` y
  `select_news_charts`. Palabras clave por activo con limites de palabra
  (sin "oil" en "turmoil" ni "oro" en "tesoro"), ponderadas por titulo vs
  resumen, impacto y posicion; maximo 3 graficos.
- `services/email_charts.py`: `render_news_charts_section`, tarjetas HTML/CSS
  sin imagenes. `render_sparkline` y la nueva seccion comparten el mismo
  grafico de columnas.
- `services/email_formatter.py`: `build_email_html` agrega la seccion despues
  de los titulares (`max_news_charts`, default 3). Aplica al morning brief y
  al market close sin cambios en los jobs.
- Tests: `tests/test_news_charts.py`.

### Scraping de noticias (optimizacion)
- `app/http_client.py` (`ResilientHttpClient`):
  - Llama `raise_for_status()` dentro del circuit breaker. Antes un 4xx/5xx
    se trataba como exito: el 5xx no se reintentaba, el breaker no lo
    contaba y el llamador parseaba la pagina de error como contenido.
    Afecta tambien a Ollama Cloud: un 5xx ahora se reintenta segun
    `OLLAMA_MAX_RETRIES`.
  - Reutiliza un `httpx.Client` por instancia (pool de conexiones) en vez de
    abrir uno por request, y envia un User-Agent propio.
- `data_sources/rss_news_client.py`:
  - Los feeds se descargan en paralelo, con un circuit breaker por host.
    `pybreaker` mantiene un lock durante toda la llamada, asi que el breaker
    global `"rss"` serializaba las descargas; ademas un feed caido podia
    abrir el circuito de todos. Medido: ~2.9s -> ~0.7s (en frio).
  - Se elimina el reintento via `feedparser.parse(url)`, que descargaba de
    nuevo sin timeout ni breaker y duplicaba la espera en feeds caidos.
  - Fechas: se usan `published_parsed`/`updated_parsed` de feedparser.
    Investing.com publica fechas no RFC 822 ("2026-09-28 19:32:38") que
    antes caian a "ahora", por lo que sus 10 notas pasaban siempre el
    filtro de recencia (y podian re-disparar alertas).
  - Se limpian tags HTML y entidades de titulos y resumenes.
- `data_sources/chile_news_client.py`: La Tercera Pulso se lee desde su RSS
  oficial (~220 KB vs ~680 KB de HTML, fecha real, 20 notas en vez de 10).
  El scraping HTML queda como respaldo; en el HTML, todas las notas quedaban
  con timestamp "ahora", se podian duplicar por selectores solapados y la
  fecha visible (hora Chile) se etiquetaba como UTC. Las tres cosas se
  corrigen.
- `jobs/common.py`: el filtro de recencia se aplica antes de deduplicar
  (menos comparaciones O(n^2) y evita perder una nota reciente porque su
  duplicado antiguo llego primero). El conteo de "high impact" usa
  `HIGH_IMPACT_THRESHOLD` en vez de un 8 fijo.
- Tests nuevos: `tests/test_rss_news_client.py`; se actualiza
  `tests/test_chile_news_client.py`.

### Pendiente / siguiente iteracion
- Calidad del analisis editorial IA (seleccion de noticias, profundidad por
  region, contexto chileno): revision de prompts en curso, no incluida en
  esta entrada.
- Reducir la latencia del paso IA (~176s documentado en 0.11.0) sigue
  pendiente; el fix de esta entrada es solo sobre la recoleccion de datos.
- USD/PEN sin fuente confiable en Yahoo y graficos IA (PNG) aun apagados:
  ver `NEXT_STEPS.md`.

## [0.13.0] - 2026-06-20

### Email (IA-first redesign)
- `services/email_formatter.py`:
  - `build_email_html` ahora acepta `nix_chart_pngs` y
    `include_deterministic_brief`.
  - La card "Analisis de Nix" se mueve al **inicio** del body (antes estaba
    al final, donde el usuario reportaba que "no se lucia"). Incluye badge
    "DMAC AI" con gradient, heading 18px, y `eyebrow` "Generado por Ollama
    Cloud / DMAC AI".
  - Nuevo gate: cuando `nix_analysis_html` esta presente y se pasa
    `include_deterministic_brief=False`, las 7 secciones deterministicas
    (Resumen ejecutivo, Chile, Latam, EE.UU., Internacional, Que mirar hoy,
    Lectura DMAC) NO se renderizan. Asi la IA reemplaza al resumen
    deterministico sin duplicar contenido.
- `services/ai/chart_renderer.py`:
  - Nueva funcion `render_charts_as_png(specs, snapshots, news) -> dict[chart_id, bytes]`
    que exporta los graficos IA como PNG via kaleido.
- `services/ai/editorial_pipeline.py`: `Phase3PipelineResult` ahora incluye
  `chart_pngs: dict[str, bytes]` ademas de los fragments Plotly.
- `services/email_sender.py`: `EmailSender.send(..., inline_images=None)`
  aceptaba imagenes inline como `cid:` adjuntos. **Esta funcionalidad se
  deshabilita en el MVP** (Outlook mobile / web mostraba icono de imagen
  rota con cid: multipart/related). El parametro se mantiene por backward
  compatibility pero se ignora.
- `jobs/morning_brief.py` y `jobs/market_close.py`:
  - Activan `render_charts_enabled` y `max_charts` en el pipeline IA.
  - Pasan `nix_chart_pngs` al builder (descartado en MVP, ver abajo).
  - `include_deterministic_brief=not bool(nix_analysis_html)`.

### MVP: visualizaciones IA deshabilitadas
- **Decision**: las visualizaciones IA (Plotly + PNG via base64 o cid) NO se
  embeben en el email productivo en MVP. El codigo de render
  (`services.ai.chart_renderer.render_charts_as_png`) se mantiene disponible
  para reactivacion futura.
- **Razon**: Outlook mobile y Outlook web mostraban icono de imagen rota con
  cid: multipart/related. La opcion base64 inline funcionaba pero inflaba el
  email ~3x (~60KB -> ~200KB) y agregaba complejidad sin valor claro vs las
  barras estaticas que ya tenemos.
- `_build_nix_charts_cid_map` en ambos jobs ahora retorna `{}` con un
  comentario claro de como reactivar.
- `_nix_analysis_section` ignora el param `nix_chart_pngs` y NO renderiza el
  bloque "Visualizaciones DMAC AI".
- **Lo que SI se mantiene**: asset table, barras de variacion %, distribucion
  por region (todas estaticas JS-free en `services/email_charts.py`).

### Documentacion
- `DEPLOY.md` (NUEVO): guia paso a paso para deployar en servidor 24/7 via
  SSH + rsync + systemd + Docker. Incluye troubleshooting, comandos utiles,
  backup, actualizacion.
- `docs/email-output.md` (NUEVO): estructura del email, comportamiento por
  cliente, notas sobre el MVP y las visualizaciones.
- `README.md`: anade links a `DEPLOY.md` y `docs/email-output.md`. La
  seccion "Deploy En Servidor" ahora apunta a `DEPLOY.md` para los detalles.

### Verificado
- 196/196 tests, ruff limpio.
- Morning brief enviado por SMTP al destinatario configurado: card IA al inicio,
  visualizaciones estaticas presentes, sin bloque "Visualizaciones DMAC AI",
  email de ~60KB.

## [0.12.0] - 2026-06-20

### Seguridad
- `app/logging_config.py`:
  - JsonFormatter redacta automaticamente parametros sensibles en mensajes
    y URLs (user, pass, password, api_key, token, Authorization, Bearer,
    ollama_api_key, bcentral_user, bcentral_password, smtp_password).
  - `_UrlRedactFilter` aplicado a `httpx` para limpiar URLs en logs HTTP.
  - `httpx` baja a WARNING por default.
- `app/config.py`:
  - `email_to`, `email_cc` y `rss_feeds` ahora son `str` y se exponen como
    propiedades `email_to_list`, `email_cc_list`, `rss_feeds_list` para
    evitar que pydantic-settings intente decodificar valores vacios como
    JSON y rompa la carga de `.env`.
- `services/email_sender.py` y `data_sources/rss_news_client.py` migrados
  a las nuevas propiedades.

### Deploy
- `.env.production.example`: plantilla lista para servidor con SMTP
  Outlook, `BCENTRAL_CREDENTIALS_FILE`, IA habilitada.
- `docker-compose.yml`:
  - Volume `./credentials:/app/credentials:ro` para credenciales externas.
  - Healthcheck Docker.
- `Dockerfile`: `curl` para healthchecks, HEALTHCHECK integrado.
- `deploy/systemd/dmac-market-brief-agent.service`: oneshot que mantiene
  el stack Docker Compose vivo.
- `deploy/install_server.sh`: script de instalacion (`sudo ./deploy/install_server.sh`).
- `.gitignore`: `.env.production.example` permitido.

### Verificado
- Email sender captura `SMTPAuthenticationError` y registra `error` en
  `storage` sin crashear.
- BCCh credentials file carga user/password.
- Sanitizacion de logs funciona: `user=<redacted>`, `pass=<redacted>`,
  `Bearer <redacted>`, `OLLAMA_API_KEY=<redacted>`.
- 189/189 tests, ruff limpio.

### Pendiente en servidor
- Reemplazar `<REEMPLAZAR_POR_APP_PASSWORD>` y `<REEMPLAZAR_POR_TU_OLLAMA_KEY>`
  en `.env` antes de levantar.
- Crear `credentials/bcentral.txt` con dos lineas (usuario y password BCCh).
- Probar `python -m app.main morning` con `DRY_RUN=false` y `EMAIL_ENABLED=true`.

---

## [0.11.0] - 2026-06-20

### Cambiado
- `prompts/ai/intermediate_report.md`: schema completo con `AiTopicCluster` (region, country, topic, relevance, news_urls, observed_facts, interpretation, affected_assets, watch_items, cautions). Checklist explicito antes de responder. Elimina schema_error cuando la IA consolida macro + micro.
- `prompts/ai/editorial_email_writer.md`:
  - Headline prohibido generico ("Mercados y coyuntura regional", "Coyuntura regional y de mercados", "DMAC Coyuntura - <fecha>"). Debe mencionar un driver especifico.
  - `source_notes` solo acepta fuentes exactas de `{{EXACT_SOURCE_NAMES}}`. No aliases ni dominios.
  - `editorial_cautions` no debe contener metadata tecnica interna.
  - Sin `change_pct_bar` ni `assets_table` si snapshots tienen `price=null`.
  - Checklist explicito antes de responder.
- `services/ai/editorial_writer.py`:
  - Pasa `{{EXACT_SOURCE_NAMES}}` al prompt con fuentes reales de news + snapshots.
  - Aplica `_filter_source_notes()` para descartar aliases o dominios no presentes en el input.
  - Helper `_collect_exact_source_names()` y `_filter_source_notes()`.
- `services/ai/schemas.py`: `AiChartSpec` valida `subtitle`, `source_label` y `title` con coerce `None -> ""` (evita rejection cuando la IA devuelve `null`).

### Verificado
- `ai-review-compare` con mock: score IA 100/100, intermediate_report valid status OK, headline especifico, fuentes exactas.
- `ai-review-compare` con datos reales: 42 noticias, score IA 96/100 (cap por chart_count=0 ya que snapshots sin precios), headline especifico, schema completo OK.
- 189/189 tests pasando, ruff limpio.

### Notas
- La key de Ollama Cloud expuesta en chat fue removida de `.env` (ahora placeholder). El usuario debe rotarla en Ollama Cloud e ingresar la nueva manualmente.
- Latencia real sigue alta (~176s con 42 noticias). Optimizar a corto plazo: reducir `AI_MAX_NEWS_ITEMS` o hacer `intermediate_report` deterministico.

---

## [0.10.0] - 2026-06-20

### Agregado
- `services/ai/quality_score.py`: Quality score v2 con 17 checks cualitativos
  - Estructurales: regional_sections, source_notes, no_duplicates, summary_points,
    charts, no_orphan_charts, cautions, subject_length, preheader_length,
    headline, preserved_news, section_count_reasonable
  - Cualitativos: headline_not_generic, reading_not_generic,
    no_raw_score_prefixes, no_topic_only_bullets,
    mentions_chile_when_present, mentions_copper_when_moving
  - Bonus por rango de graficos (1-4) y diversidad de fuentes (>=3)
  - Cap blando a 96 cuando `fallback_used=True` o `chart_count=0`
  - Output incluye `quality_version=v2`, contadores cualitativos
- `services/ai/editorial_writer.py`: Fallback editorial mejorado
  - Lectura preliminar por topic (bancos centrales, politica fiscal, commodities,
    forex, mercados) con clausulas separadas y un solo prefijo "Lectura preliminar:"
  - Headline templates v2: "X y Y marcan la jornada", "Z lidera la jornada",
    "Y: foco en T" (ya no usa "marcan la agenda" plano)
  - Executive summary usa ultimo bullet por seccion (>=2) para evitar duplicados
  - Topic headers en bullets en formato `**En X:**` (bold lead-in) en vez de bullet suelto
  - Variables internas: `topic_groups` ya no se vacia por duplicacion
- `services/ai/{macro_router,topic_router,editorial_writer}.py`,
  `services/ai/pipeline.py`, `services/ai/editorial_pipeline.py`:
  - Parametro opcional `settings: Settings | None = None` para inyectar
    `Settings` con override de `ollama_model` y `ai_dry_run`
  - Permite ejecutar el mismo pipeline con multiples modelos Ollama
- `jobs/ai_review_compare.py`: Nuevo job `run_ai_review_compare`
  - Genera `outputs/ai/compare_reviews/YYYYMMDD_HHMM/`
  - `fallback/`: bundle completo del fallback deterministico
  - `models/<safe_model>/`: un bundle por modelo listado en `OLLAMA_COMPARE_MODELS`
  - `comparison_report.md` y `comparison_summary.json` con tabla comparativa
  - Funciona sin `OLLAMA_API_KEY` (solo fallback) y avisa como habilitar
  - Variables: `OLLAMA_COMPARE_MODELS`, `AI_COMPARE_USE_MOCK`
- `app/main.py`: Comando CLI `ai-review-compare`
- `tests/test_ai_review_compare.py`: 3 tests
  - sin key genera solo fallback
  - con dry-run activo skipea IA
  - con IA ready corre un variant por modelo

### Modificado
- `services/ai/editorial_writer.py`: `_build_editorial_paragraph` usa
  `_build_topic_reading` con frases por topic en vez de generica
- `services/ai/editorial_writer.py`: `_build_subject_and_headline` ahora
  usa `_build_headline` con templates limpios
- `jobs/ai_review_fast.py` y `jobs/ai_review_sample.py`:
  - Pasan `snapshots` y `news` a `compute_quality_score`
  - Pasan `fallback_used` para activar el cap del score

### Notas
- Quality score 96/100 estable con fallback (cap activado)
- Quality score < 100 reservalo a corridas IA reales con charts
- `ai-review-compare` es el gate para evaluar modelos Ollama Cloud
  antes de integrarlos al pipeline productivo

---

## [0.9.0] - 2026-06-20

### Agregado
- `services/ai/quality_score.py`: Quality score MVP (0-100) con 11 checks
  - has_regional_sections, has_source_notes, has_no_duplicate_titles
  - has_minimum_summary_points, has_charts, has_no_orphan_charts
  - has_cautions, has_valid_subject_length, has_valid_preheader_length
  - has_headline, preserved_news
  - bonus por rango de graficos (1-4) y diversidad de fuentes (>=3)
- `jobs/ai_review_fast.py`: Job con dataset mock fijo para iteracion rapida
  - No requiere RSS/scraping ni yfinance
  - Guarda en outputs/ai/fast_reviews/ en vez de outputs/ai/reviews/
- Comando CLI: `ai-review-fast` en app/main.py
- `quality_score.json` en review bundle
- Quality Score en `review_checklist.md`

### Modificado
- `services/ai/editorial_writer.py`: `build_deterministic_editorial()` refactorizado
  - Sin titulos duplicados en bullets
  - Estructura editorial: parrafo de hechos + lectura preliminar
  - `subject` deterministico con top regions/assets: `DMAC Coyuntura: cobre, Chile, ...`
  - `headline` deterministico: `cobre, Chile, y bancos centrales marcan la agenda`
  - `preheader` deterministico: `Foco en Chile. topics: ..., forex. Cobre +3.00%`
  - `executive_summary` con fallback a top 2 secciones regionales
  - Helpers: `_strip_score_prefix`, `_build_editorial_paragraph`,
    `_default_executive_summary`, `_build_subject_and_headline`
- `services/ai/review_checklist.py`: `build_review_checklist()` incluye Quality Score
- `services/ai/review_checklist.py`: `save_review_bundle()` acepta `quality_score_json`
- `jobs/ai_review_sample.py`: Calcula y guarda quality_score.json
- `app/main.py`: Comando `ai-review-fast` agregado

### Notas
- Quality score 100/100 en corrida ai-review-fast con datos mock
- Subject, headline y preheader ahora son dinamicos y mencionan cobre/top regions
- Sin duplicacion de titulares en bullets (validado con test)
- ai-review-fast es para iteracion rapida de prompts y formato
- ai-review sigue siendo para corridas con datos reales (RSS + scraping)

---

## [0.8.0] - 2026-06-20

### Agregado
- `tests/test_no_news_loss.py`: 8 tests que verifican que RSS/scraping no se pierden en fallback
- `tests/test_copper_symbol_isolation.py`: 7 tests que verifican que HG=F no aparece en outputs IA
- Review bundle ahora guarda `input_news.json`, `input_snapshots.json`, `source_summary.json`
- `source_summary.json`: conteo por fuente, region y topic de las noticias de input
- `review_summary.json` ahora incluye `phase2_regional_reports_count` y `source_count`
- Known issues automaticos detectan perdida de noticias (news > 0 pero sin regional_reports)

### Modificado
- `services/ai/pipeline.py`: Fallback deterministico robusto usando routed_news
  - `_build_deterministic_fallback()`: agrupa por pais/region, crea topic clusters con titulares reales
  - `_build_deterministic_topic_clusters()`: agrupa por topic con observed_facts y news_urls
  - Pipeline detecta groups vacios (no solo IA fallo) y usa fallback
- `services/ai/editorial_writer.py`: Fallback editorial lista titulares por region/topic
  - `build_deterministic_editorial()` ahora acepta news para extraer source_notes
  - Bullets incluyen topic headers y titulares reales
  - source_notes se extraen de las news items originales
- `services/ai/editorial_pipeline.py`: Phase3PipelineResult incluye phase2_report e inputs
- `services/ai/review_checklist.py`: `save_review_bundle()` guarda input_news/snapshots/source_summary
- `services/ai/review_checklist.py`: `_detect_known_issues()` detecta perdida de noticias
- `jobs/ai_review_sample.py`: Guarda phase2_report real (no metadata reconstruida)

### Notas
- El fallback deterministico ahora preserva titulares RSS/scraping en el email editorial
- Cuando IA devuelve groups vacios (dry-run), el pipeline usa fallback con noticias reales
- COPPER se usa como simbolo editorial; HG=F solo existe en data_sources/yfinance_client.py
- El review bundle es totalmente trazable: input -> fase2 -> fase3 -> email final

---

## [0.7.0] - 2026-06-20

### Agregado
- `services/ai/review_checklist.py`: Generador de checklist editorial MVP
  - Resumen de corrida (fallback, counts, known issues)
  - Checklist con criterios: claridad, trazabilidad, prudencia, estructura, graficos, decision
  - Deteccion automatica de problemas (graficos huerfanos, exceso de graficos, campos vacios)
  - save_review_bundle() para guardar carpeta completa de revision
- `jobs/ai_review_sample.py`: Job que genera bundle completo de revision en outputs/ai/reviews/
- Comandos CLI: `ai-phase2`, `ai-phase3`, `ai-review` en app/main.py
- Tests: 10 nuevos (test_ai_review_checklist)

### Modificado
- `services/ai/editorial_writer.py`: Agregado max_charts param con priorizacion de graficos
  - _prioritize_chart_ids(): orden change_pct > impact_ranking > assets_table > region > topic
  - _limit_chart_specs(): limita chart_specs y chart_ids en secciones
- `services/ai/editorial_pipeline.py`: Passthrough de max_charts al editorial writer
- `jobs/ai_phase3_editorial_email.py`: Pasa ai_max_charts desde settings
- `app/main.py`: Agregados comandos ai-phase2, ai-phase3, ai-review

### Notas
- Fase 4 MVP Review Loop: genera carpetas de revision autocontenidas para afinar outputs
- Cada review se guarda en outputs/ai/reviews/YYYYMMDD_HHMM/ con todos los archivos + checklist
- Graficos limitados a AI_MAX_CHARTS (default 4) por prioridad editorial
- El checklist incluye secciones de claridad, trazabilidad, prudencia financiera, estructura y graficos
- Deteccion automatica de problemas conocidos (fallback, campos vacios, graficos huerfanos)

---

## [0.6.0] - 2026-06-20

### Agregado
- `services/ai/editorial_writer.py`: Agente IA que convierte reporte Fase 2 en email editorial
- `services/ai/chart_renderer.py`: Renderizador deterministico de graficos con Plotly
  - 5 tipos: bar_change_pct, bar_impact_ranking, bar_news_by_region, bar_news_by_topic, table_assets
  - available_chart_ids() evalua que graficos son viables segun datos disponibles
- `services/ai/editorial_email_formatter.py`: Render HTML + Markdown del email editorial
- `services/ai/editorial_pipeline.py`: Orquestador Fase 3 (phase2 -> editorial -> charts -> HTML)
- `jobs/ai_phase3_editorial_email.py`: Job manual para generar email editorial preview
- `prompts/ai/editorial_email_writer.md`: Prompt para redaccion editorial narrativa
- Schemas Fase 3: AiChartSpec, AiEditorialSection, AiEditorialEmail, AiEditorialRunMetadata, AiPhase3RunResult
- Tests: 45 nuevos (phase3_schemas, editorial_writer, chart_renderer, email_formatter, phase3_pipeline)
- `requirements.txt`: Agregada dependencia plotly==5.24.1

### Modificado
- `app/config.py`: Agregadas settings AI_CHARTS_ENABLED, AI_MAX_CHARTS, AI_CHART_OUTPUT_DIR
- `.env.example`: Documentadas nuevas variables Fase 3
- `tests/test_prompt_loader.py`: Validacion de prompt editorial_email_writer
- `services/ai/schemas.py`: Agregados schemas Fase 3 al final

### Notas
- Fase 3 es preview-only: genera HTML + graficos pero NO envia emails ni toca SMTP
- Los graficos se renderizan con Plotly via CDN (para preview en browser)
- El email editorial se guarda en outputs/ai/ como JSON + Markdown + HTML
- Los graficos individuales se guardan en outputs/ai/charts/
- Fallback deterministico si IA falla o JSON es invalido
- La IA sugiere chart_specs pero el renderer solo acepta ids del catalogo valido
- Chart catalog fijo: change_pct_bar, impact_ranking_bar, news_by_region_bar, news_by_topic_bar, assets_table

---

## [0.5.0] - 2026-06-20

### Agregado
- `services/ai/grouping.py`: Country inference + agrupacion deterministica
- `services/ai/macro_router.py`: Router macro por region/pais via Ollama Cloud
- `services/ai/topic_router.py`: Router micro por topic dentro de cada region
- `services/ai/pipeline.py`: Orquestador secuencial Fase 2 (macro -> micro -> reporte)
- `jobs/ai_phase2_report.py`: Job manual para generar reporte intermedio IA
- `prompts/ai/macro_region_router.md`: Prompt para agrupacion macro
- `prompts/ai/topic_micro_router.md`: Prompt para agrupacion micro por topic
- `prompts/ai/intermediate_report.md`: Prompt para consolidacion de reporte
- Schemas Fase 2: AiRoutedNewsInput, AiMacroRouterResponse, AiTopicRouterResponse, AiPhase2Report, etc.
- Tests: 31 nuevos (phase2_schemas, grouping, macro_router, topic_router, pipeline, prompt_loader)

### Modificado
- `app/config.py`: Agregadas settings AI_OUTPUT_DIR, AI_MAX_GROUPS, AI_MAX_NEWS_PER_GROUP
- `.env.example`: Documentadas nuevas variables Fase 2
- `tests/test_prompt_loader.py`: Validacion de nuevos prompts

### Notas
- Fase 2 es un pipeline paralelo: no reemplaza email productivo ni scraping
- Reportes se guardan en outputs/ai/ como JSON + Markdown + metadata
- Fallback deterministico si Ollama Cloud falla o JSON es invalido
- Country inference deterministica (Chile, EE.UU., Eurozona, Brasil, Mexico, China, etc.)

---

## [0.4.0] - 2026-06-20

### Agregado
- `services/ai/`: Capa de IA para analisis de noticias y redaccion
  - `ollama_client.py`: Cliente Ollama Cloud con dry-run y reintentos
  - `schemas.py`: Schemas Pydantic (AiSmokeTestResponse, AiBriefDraft, etc.)
  - `prompt_loader.py`: Cargador de prompts desde prompts/ai/
  - `json_validation.py`: Extraccion y validacion estricta de JSON
  - `smoke_test.py`: Smoke test sobre noticias ya recolectadas
- `prompts/ai/`: Prompts para agentes
  - `system_financial_editor.md`: System prompt editorial
  - `json_smoke_test.md`: Prompt para smoke test
- Tests: 18 nuevos (schemas, prompt_loader, ollama_client, json_validation, smoke_test)

### Modificado
- `app/config.py`: Agregadas settings de IA (AI_ENABLED, AI_DRY_RUN, OLLAMA_*)
- `.env.example`: Documentadas variables de Ollama Cloud

### Notas
- La IA no reemplaza scraping ni recoleccion de datos
- AI_ENABLED=false mantiene comportamiento deterministico
- AI_DRY_RUN=true no llama a la red
- El modelo solo analiza noticias ya recolectadas y filtradas

---

## [0.3.0] - 2026-06-20

### Agregado
- `app/http_client.py`: Cliente HTTP con retry y circuit breaker
  - Pybreaker para circuit breaker pattern
  - Exponential backoff para reintentos
  - Circuit breaker por fuente (rss, chile_news)
- `services/news_classifier.py`: Memoizacion de funciones de normalizacion
  - `normalize_text()` ahora usa `lru_cache`
  - `_similarity_ratio()` ahora usa `lru_cache`
- `services/impact_scoring.py`: Scoring granular para movimientos de mercado
  - Puntos proporcionales segun magnitud vs threshold
  - Maximo 6 puntos por movimientos (antes maximo 2)
- `jobs/common.py`: Logging estructurado por paso
  - Logs de inicio, snapshots, RSS, Chile, clasificacion, scoring
  - Conteo de items de alto impacto

### Modificado
- `data_sources/chile_news_client.py`:
  - Ahora usa ResilientHttpClient con retry y circuit breaker
  - Mejor extraccion de timestamps (datetime parsing)
- `data_sources/rss_news_client.py`:
  - Ahora usa ResilientHttpClient con retry y circuit breaker
- `requirements.txt`: Agregadas dependencias pybreaker y cachetools

---

## [0.2.0] - 2026-06-20

### Agregado
- `data_sources/chile_news_client.py`: Cliente de scraping para fuentes chilenas
  - Ministerio de Hacienda: comunicados de politica fiscal
  - La Tercera Pulso: negocios y economia chilena
- `pyproject.toml`: Configuracion de proyecto con ruff y pytest
- `tests/test_chile_news_client.py`: Tests unitarios para cliente de scraping

### Modificado
- `data_sources/rss_news_client.py`: Depurado a 5 fuentes funcionales
  - Eliminados feeds rotos: BCCh, CMF, INE, Hacienda, BLS, BEA, IMF, World Bank
  - Conservados: Federal Reserve, ECB, Financial Times, MarketWatch, Investing.com
- `jobs/common.py`: Integracion de ChileNewsClient en pipeline de noticias
- `requirements.txt`: Agregadas dependencias beautifulsoup4 y lxml para scraping
- `.env.example`: Documentacion de RSS_FEEDS
- `README.md`: Actualizada seccion de fuentes de datos y roadmap

### Removido
- EMOL Economia del cliente de scraping (feed no funcional - redirect a pagina principal)

---

## [0.1.0] - MVP Inicial

### Fuentes de datos
- BCCh API para TPM e IPC
- yfinance para precios de activos
- RSS feeds (8 fuentes originales, 80% rotas)
