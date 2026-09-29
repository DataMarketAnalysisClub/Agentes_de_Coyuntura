# dmac-market-brief-agent

Agente de coyuntura financiera para el Data Market Analysis Club UDD. El proyecto recolecta datos de mercado, titulares economicos y eventos relevantes para generar Morning Brief, Market Close y correos HTML automaticos.

El MVP prioriza simpleza, bajo costo, auditoria y mantenibilidad por estudiantes.

## Funcionalidades

- Morning Brief diario con texto y correo HTML.
- Market Close diario con movimientos relevantes y posibles drivers.
- Formato ejecutivo: maximo 3 titulares seleccionados por calidad editorial.
- Seccion de sentimiento de mercado con visualizacion 0-100 y drivers principales.
- Monitor de alertas de alto impacto financiero desactivado por defecto.
- Analisis editorial IA (Ollama Cloud) que reemplaza el resumen deterministico
  cuando esta disponible.
- Visualizaciones estaticas en el email (asset table y distribucion por region).
  Render JS-free, compatibles con todos los clientes.
- Persistencia auditable en SQLite.
- Envio SMTP opcional con `DRY_RUN` por defecto.
- Tolerancia a fallas de APIs externas.
- Scheduler interno con APScheduler.
- Docker y Docker Compose.

## Documentacion

- [DEPLOY.md](DEPLOY.md): guia completa para desplegar en servidor 24/7 via
  SSH + rsync + systemd + Docker.
- [docs/email-output.md](docs/email-output.md): estructura del email,
  comportamiento por cliente, y notas sobre el MVP.

## Arquitectura

- `app/`: CLI, configuracion, logging y scheduler.
- `data_sources/`: conectores externos - yfinance, BCCh API, RSS feeds, scraping Chile.
- `services/`: logica de negocio, scoring, clasificacion, formatos, email e IA.
- `services/ai/`: cliente Ollama Cloud, schemas, prompts y validacion JSON.
- `jobs/`: Morning Brief, Market Close y monitor de alertas.
- `storage/`: SQLite, modelos y repositorios.
- `prompts/`: guias editoriales y prompts para agentes IA.
- `prompts/ai/`: prompts operativos para Ollama Cloud.
- `outputs/`: briefs, alertas y artefactos IA generados.
- `tests/`: tests unitarios sin llamadas externas.

### Fuentes de Datos

**Datos economicos:**
- BCCh API (requiere credenciales; codigos verificados con `SearchSeries`
  el 2026-09-29). Las series se piden en paralelo con yfinance; los dias sin
  dato (`NaN`) se ignoran.
  - Indicadores (nivel, periodo y cambio en pp contra el dato anterior):
    TPM (`F022.TPM.TIN.D001.NO.Z.D`), IPC 12 meses
    (`F074.IPC.V12.Z.EP23.C.M`, base 2023), IPC mensual
    (`F074.IPC.VAR.Z.Z.C.M`), IMACEC 12 meses
    (`F032.IMC.V12.Z.Z.2018.Z.Z.0.M`) y desempleo INE, trimestre movil no
    ajustado (`F049.DES.TAS.INE9.10.M`).
  - Series diarias con ~1 mes de historia: dolar observado
    (`F073.TCO.PRE.Z.D`), UF (`F073.UFF.PRE.Z.D`; se pide hasta hoy porque
    el BCCh publica la UF por adelantado), cobre refinado BML en USD/lb
    (`F019.PPB.PRE.100.D`) y USD/PEN (`F072.PEN.USD.N.O.D`). Una serie
    diaria con mas de 7 dias de antiguedad no se muestra. El dolar observado
    y el cobre BML son referencias oficiales junto a los precios intradia de
    Yahoo, no los reemplazan.
  - El IPSA del BCCh (`F013.IBC.IND.N.7.LAC.CL.CLP.BLO.M`) es solo mensual:
    el IPSA diario sigue viniendo de Yahoo.
- yfinance (`1.7.0`, fijada): precios de activos (USDCLP, COPPER, IPSA,
  SP500, etc.) y ~1 mes de cierres diarios para las sparklines del correo.
  Unica fuente de datos de mercado (Google Finance se retiro del pipeline).
  - IPSA: fuente aprobada `MXIPSAGC.SN` (decision del club, 2026-09-29),
    con velas horarias porque su historial diario en Yahoo viene incompleto;
    20 min de retraso. Yahoo lo rotula "MSCI IPSA INDEX (con dividendos)",
    pero su nivel coincide con el S&P IPSA. Alternativas evaluadas y
    descartadas: `^IPSA` y `SPCLXIPSA.SN` (sin datos), `SPIPSA.SN` y
    findic.cl (congelados al 31-08-2026), BCCh (solo promedio mensual), API
    Brain Data de la Bolsa de Santiago (requiere cuenta y revisar terminos
    de redistribucion) e Investing.com (scraping).
  - Series con velas inconsistentes (cierre fuera de maximo/minimo) o con
    ultimo cierre de hace mas de 7 dias se descartan y se muestran como
    "s/d". Por eso USD/PEN salio de yfinance (`PEN=X` traia velas
    inconsistentes) y se toma del BCCh.

**Noticias RSS (5 fuentes funcionales, descargadas en paralelo):**
- Federal Reserve (EE.UU. macro)
- ECB (Eurozona)
- Financial Times (global)
- MarketWatch (mercados EE.UU.)
- Investing.com (forex, commodities)

**Noticias Chile:**
- La Tercera Pulso: negocios y economia chilena. Se lee desde su RSS oficial
  (Arc Publishing, con fecha de publicacion real); el scraping del HTML del
  canal queda solo como respaldo si el RSS no entrega notas.
- Diario Financiero: RSS de portada (`df.cl/noticias/site/list/port/rss.xml`).
  Solo se usan titulo, bajada y link del feed (no se descarga el articulo).
  Se conservan las secciones Mercados, Economia y Politica, Empresas,
  Internacional y Primer Click; Opinion, Regiones y suplementos se descartan.
- Ambas fuentes chilenas se descargan en paralelo, cada una con su propio
  circuit breaker.

## IA y Ollama Cloud

El proyecto integra Ollama Cloud para analisis de noticias y redaccion editorial. La IA **no recolecta datos** ni reemplaza las fuentes existentes. Solo analiza noticias ya recolectadas y filtradas.

### Configuracion

```env
AI_ENABLED=false
AI_DRY_RUN=true
AI_STRICT_JSON=true
AI_MAX_NEWS_ITEMS=30
OLLAMA_BASE_URL=https://ollama.com
OLLAMA_API_KEY=
OLLAMA_MODEL=gpt-oss:120b
OLLAMA_TIMEOUT_SECONDS=45
OLLAMA_TEMPERATURE=0.2
OLLAMA_MAX_RETRIES=2
```

### Comportamiento

- `AI_ENABLED=false`: la IA no se ejecuta, pipeline deterministico.
- `AI_DRY_RUN=true`: se construye el payload pero no se llama a la red.
- `AI_DRY_RUN=false` con `AI_ENABLED=true`: llamada real a Ollama Cloud.

### Reglas de la IA

- No inventa datos, precios, fechas ni URLs.
- Solo usa noticias ya recolectadas por RSS y scraping.
- Devuelve JSON validado con Pydantic.
- Si falla, el pipeline usa fallback deterministico.
- No genera recomendaciones de inversion.

### Fase 2: Router Macro + Micro

Pipeline paralelo que agrupa noticias por region/pais y topic, generando reportes intermedios estructurados.

```bash
.venv/bin/python -m jobs.ai_phase2_report
```

Outputs en `outputs/ai/`:
- `YYYYMMDD_HHMM_phase2_report.json` - Reporte estructurado
- `YYYYMMDD_HHMM_phase2_report.md` - Reporte en markdown
- `YYYYMMDD_HHMM_phase2_metadata.json` - Metadata de auditoria

Flujo:
1. Collect market + news (existente)
2. Preprocesamiento: country inference + orden por impacto
3. Macro router: agrupa por region/pais via Ollama Cloud
4. Topic router: agrupa por topic dentro de cada region
5. Intermediate report: consolida macro + micro
6. Fallback deterministico si IA falla

### Fase 3: Email Editorial + Graficos

Pipeline que consume el reporte Fase 2 y genera un email editorial estilo noticiero financiero con graficos deterministicos (Plotly). **Preview-only**: no envia emails ni toca SMTP.

```bash
.venv/bin/python -m jobs.ai_phase3_editorial_email
```

Outputs en `outputs/ai/`:
- `YYYYMMDD_HHMM_editorial_email.json` - Email estructurado
- `YYYYMMDD_HHMM_editorial_email.md` - Version markdown (sin graficos)
- `YYYYMMDD_HHMM_editorial_email.html` - HTML preview con graficos embebidos
- `YYYYMMDD_HHMM_editorial_metadata.json` - Metadata de auditoria
- `charts/{chart_id}.html` - Graficos individuales

Flujo:
1. Phase 2 pipeline (macro -> micro -> reporte intermedio)
2. Editorial writer: convierte reporte en narrativa editorial (IA o fallback)
3. Chart renderer: renderiza graficos con Plotly desde datos disponibles
4. Email formatter: compone HTML + Markdown final

Graficos disponibles:
- `impact_ranking_bar`: ranking de noticias por impacto
- `news_by_region_bar`: distribucion de noticias por region
- `news_by_topic_bar`: distribucion de noticias por topic
- `assets_table`: tabla de principales activos

En el email productivo se usan visualizaciones JS-free: tabla de activos,
sentimiento de mercado y distribucion regional de titulares. Los graficos IA se
mantienen para preview/review, no se embeben en el email productivo.

### Fase 4: MVP Review Loop

Genera carpetas de revision autocontenidas para afinar prompts, graficos y estructura editorial antes de integrar envio real.

```bash
.venv/bin/python -m app.main ai-review
```

Cada corrida genera una carpeta en `outputs/ai/reviews/YYYYMMDD_HHMM/`:

```txt
phase2_report.json        - Reporte Fase 2
editorial_email.json      - Email estructurado Fase 3
editorial_email.md        - Version markdown
editorial_email.html      - HTML preview con graficos
metadata.json             - Metadata de auditoria de todas las etapas IA
review_summary.json       - Resumen de la corrida (fallback, counts, issues)
quality_score.json        - Quality score MVP (0-100) con checks individuales
review_checklist.md       - Checklist editorial + quality score
input_news.json           - Noticias de input (RSS + scraping)
input_snapshots.json      - Snapshots de input
source_summary.json       - Conteos por fuente, region, topic
charts/{chart_id}.html    - Graficos individuales
```

El `review_checklist.md` incluye criterios de revision agrupados en:
- **Claridad**: asunto, headline, resumen ejecutivo
- **Trazabilidad**: hechos respaldados, sin datos inventados
- **Prudencia financiera**: sin recomendaciones, separacion hechos/interpretacion
- **Estructura**: cobertura regional, no repeticion
- **Graficos**: aportan al relato, no redundantes
- **Decision**: aprobado / requiere ajuste

El `quality_score.json` es un score MVP (0-100) con checks automaticos:
- regionales, source notes, no duplicate titles
- minimum summary points, charts, no orphan charts
- cautions, subject length, preheader length, headline
- preserved news

A partir de v0.10 el score se endurece a v2 con 17 checks cualitativos:
- `headline_not_generic`, `reading_not_generic`
- `no_raw_score_prefixes`, `no_topic_only_bullets`
- `mentions_chile_when_present`, `mentions_copper_when_moving`
- `section_count_reasonable`
- Cap blando a 96 cuando `fallback_used=True` o `chart_count=0`
- Reserva 100/100 a corridas IA reales con charts

Los graficos se limitan a `AI_MAX_CHARTS` (default 4) por prioridad editorial:
1. `impact_ranking_bar` (noticias por impacto)
2. `assets_table` (tabla de activos)
3. `news_by_region_bar` / `news_by_topic_bar`

Para iteracion rapida sin esperar RSS/scraping:

```bash
.venv/bin/python -m app.main ai-review-fast
```

Usa un dataset mock fijo y guarda en `outputs/ai/fast_reviews/YYYYMMDD_HHMMSS/`.

### Fase 6: Comparador Fallback vs IA

Compara el fallback deterministico contra uno o varios modelos Ollama Cloud sobre el mismo input.

```bash
.venv/bin/python -m app.main ai-review-compare
```

Variables opcionales:

```env
OLLAMA_COMPARE_MODELS=gpt-oss:120b,otro-modelo
AI_COMPARE_USE_MOCK=true
```

Por defecto usa `OLLAMA_MODEL`. Si `OLLAMA_API_KEY` esta vacia o `AI_DRY_RUN=true`, solo se genera el bundle `fallback/` y el `comparison_report.md` explica como habilitar la comparacion IA real.

Output en `outputs/ai/compare_reviews/YYYYMMDD_HHMM/`:

```txt
input_news.json
input_snapshots.json
source_summary.json
comparison_report.md
comparison_summary.json
fallback/
  phase2_report.json
  editorial_email.json
  editorial_email.md
  editorial_email.html
  metadata.json
  quality_score.json
  review_summary.json
  review_checklist.md
  charts/
models/<safe_model>/
  ...
```

## Instalacion Local

Requiere Python 3.11 o superior.

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt  # incluye pytest y ruff
cp .env.example .env
```

Edita `.env` segun corresponda. No agregues credenciales reales al repositorio.

## Configuracion

Variables principales:

- `DRY_RUN=true`: genera archivos y registra emails sin enviarlos.
- `EMAIL_ENABLED=false`: desactiva envio de briefs.
- `ALERT_EMAIL_ENABLED=false`: desactiva envio de alertas.
- `DATABASE_URL=sqlite:///storage/dmac_market_brief.db`: base SQLite local.
- `RSS_FEEDS=`: lista opcional de URLs RSS separadas por coma.
- `HIGH_IMPACT_THRESHOLD=8`: umbral para generar alertas.
- `ALERT_DEDUP_HOURS=3`: ventana de deduplicacion de alertas.
- `BCENTRAL_CREDENTIALS_FILE=`: archivo externo con credenciales BCCh en dos lineas.

SMTP:

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USER`
- `SMTP_PASSWORD`
- `EMAIL_FROM`
- `EMAIL_TO`
- `EMAIL_CC`
- `EMAIL_LOGO_URL`: URL HTTPS del logo del correo (por defecto el PNG del
  repo en GitHub). Vacio: se incrusta `assets/Dmac_logo.png` como `data:`,
  que Gmail y Outlook web no muestran (solo para previews locales).
- `OPS_EMAIL_TO`: mantenedores que reciben los avisos de salud de fuentes
  (separados por coma). Vacio: los cambios de estado solo quedan en el log.
  Nunca se usa la lista del club para estos avisos.

Salud de fuentes:

Cada corrida (manana, cierre y monitor) compara lo que llego contra lo
esperado: feeds sin notas o con notas viejas, activos sin precio o con saltos
poco plausibles. Una fuente cambia de estado tras dos corridas malas seguidas
y se avisa a `OPS_EMAIL_TO`. El correo muestra el ultimo precio valido
rotulado "al DD-MM" cuando un activo no trae datos, y lista las fuentes sin
datos al final. Estado actual:

```bash
python -m app.main health
```

Banco Central de Chile:

- `BCENTRAL_USER`: usuario BCCh. Puede omitirse si se usa `BCENTRAL_CREDENTIALS_FILE`.
- `BCENTRAL_PASSWORD`: contrasena BCCh. Puede omitirse si se usa `BCENTRAL_CREDENTIALS_FILE`.
- `BCENTRAL_CREDENTIALS_FILE`: ruta a archivo externo no versionado. Formato esperado: primera linea correo, segunda linea contrasena.
- `BCENTRAL_TPM_SERIES`: serie para TPM. Default: `F022.TPM.TIN.D001.NO.Z.D`.
- `BCENTRAL_IPC_SERIES`: IPC variacion mensual. Default: `F074.IPC.VAR.Z.Z.C.M`.
- `BCENTRAL_UNEMPLOYMENT_SERIES`: tasa de desocupacion (INE). Default: `F049.DES.TAS.INE9.10.M`.
- `BCENTRAL_USDPEN_SERIES`: soles peruanos por dolar. Default: `F072.PEN.USD.N.O.D`.
- `BCENTRAL_IPC12_SERIES`: IPC variacion 12 meses. Default: `F074.IPC.V12.Z.EP23.C.M`.
- `BCENTRAL_IMACEC_SERIES`: IMACEC variacion 12 meses. Default: `F032.IMC.V12.Z.Z.2018.Z.Z.0.M`.
- `BCENTRAL_DOLAR_OBSERVADO_SERIES`: dolar observado. Default: `F073.TCO.PRE.Z.D`.
- `BCENTRAL_UF_SERIES`: valor diario de la UF. Default: `F073.UFF.PRE.Z.D`.
- `BCENTRAL_COPPER_SERIES`: cobre refinado BML (USD/lb). Default: `F019.PPB.PRE.100.D`.
- `BCENTRAL_TIMEOUT_SECONDS`: timeout HTTP para BCCh.

Ejemplo local seguro:

```bash
BCENTRAL_CREDENTIALS_FILE=/ruta/local/credenciales_bcch.txt
```

No copies el contenido de ese archivo a Git ni a mensajes de error.

## Ejecucion Manual

```bash
.venv/bin/python -m app.main morning
.venv/bin/python -m app.main close
.venv/bin/python -m app.main monitor-once
.venv/bin/python -m app.main scheduler
.venv/bin/python -m app.main ai-phase2
.venv/bin/python -m app.main ai-phase3
.venv/bin/python -m app.main ai-review
.venv/bin/python -m app.main ai-review-fast
.venv/bin/python -m app.main ai-review-compare
```

Los archivos se guardan en:

- `outputs/briefs/`
- `outputs/alerts/`

## Docker

Desarrollo local:

```bash
cp .env.example .env
docker compose build
docker compose up -d
```

El contenedor ejecuta `python -m app.main scheduler` por defecto y monta:

- `./outputs:/app/outputs`
- `./logs:/app/logs`
- `./storage:/app/storage`
- `./credentials:/app/credentials:ro` (read-only)

Validar configuracion:

```bash
docker compose config --no-interpolate
```

Evita ejecutar `docker compose config` sin `--no-interpolate` si tienes un
`.env` real, porque Docker puede imprimir secretos expandidos en la salida.

## Deploy En Servidor (Produccion)

La guia completa de despliegue (prerequisitos, configuracion de `.env`,
instalacion systemd, troubleshooting, actualizaciones) esta en
[DEPLOY.md](DEPLOY.md). Resumen rapido:

1. Limpiar el bundle local (`outputs/`, `logs/`, `__pycache__/`, etc.)
2. Subir al servidor via `rsync` (excluyendo `.venv`, `__pycache__`,
   `outputs/`, `storage/*.db`, `.git`)
3. En el servidor: `cp .env.production.example .env && nano .env`
   (llenar `OLLAMA_API_KEY`, `SMTP_PASSWORD`, `EMAIL_TO`)
4. `chmod 600 .env && chmod 700 credentials/`
5. `sudo ./deploy/install_server.sh`
6. Verificar: `systemctl status dmac-market-brief-agent`

### Variables Clave (resumen)

- `SMTP_HOST=smtp.gmail.com`
- `SMTP_PORT=587`
- `SMTP_USER=notifications@example.com`
- `SMTP_PASSWORD=<Gmail App Password>`
- `EMAIL_FROM=notifications@example.com`
- `EMAIL_TO=recipient@example.com`
- `BCENTRAL_CREDENTIALS_FILE=/app/credentials/bcentral.txt`
- `AI_ENABLED=true`
- `AI_DRY_RUN=false`
- `OLLAMA_API_KEY=<key>`

### Horarios Scheduler

- Morning brief: lunes a viernes 08:30 America/Santiago.
- Market close: lunes a viernes 18:30 America/Santiago.
- High impact monitor: desactivado por defecto. Solo corre si `ALERT_MONITOR_ENABLED=true`.

Para troubleshooting detallado, comandos de monitoreo, backup, y updates
futuros ver [DEPLOY.md](DEPLOY.md).

## Seguridad

- Ninguna credencial aparece en logs (redactadas por `app/logging_config.py`).
- Credenciales BCCh siempre en archivo externo (`BCENTRAL_CREDENTIALS_FILE`).
- `.env` con permisos 600.
- Volumen `credentials` montado read-only.
- Revisar `git status` antes de commitear nada.

## Tests

```bash
.venv/bin/python -m pytest
```

Los tests actuales no dependen de APIs externas.

## Agregar Nuevas Fuentes

1. Crea o actualiza un cliente en `data_sources/`.
2. Devuelve datos normalizados y tolera errores con logs `warning`.
3. Integra la fuente en un servicio de `services/` o job de `jobs/`.
4. Agrega tests con mocks o fakes.

Para RSS, puedes usar `RSS_FEEDS` en `.env` con URLs separadas por coma.

## Agregar Nuevos Activos

1. Agrega el ticker en `DEFAULT_ASSETS` de `data_sources/yfinance_client.py`.
2. Si aplica, agrega umbral en `MOVEMENT_THRESHOLDS` de `services/impact_scoring.py`.
3. Agrega o ajusta tests.

## Activar Correo

1. Configura SMTP en `.env`.
2. Define `EMAIL_TO` y opcionalmente `EMAIL_CC` separados por coma.
3. Cambia `DRY_RUN=false`.
4. Cambia `EMAIL_ENABLED=true` para briefs.
5. Mantén `ALERT_MONITOR_ENABLED=false` salvo que se requieran alertas manualmente.

Nunca imprimas ni commitees credenciales.

## GitHub

Ramas sugeridas:

- `main`
- `develop`
- `feature/data-sources`
- `feature/email-delivery`
- `feature/impact-alerts`
- `feature/docker-deployment`

Commits sugeridos:

- `chore: initialize project structure`
- `feat: add market snapshot service`
- `feat: add rss news ingestion`
- `feat: add impact scoring`
- `feat: add brief formatters`
- `feat: add smtp email sender`
- `feat: add scheduled jobs`
- `feat: add docker deployment`
- `test: add initial unit tests`
- `docs: add setup and usage instructions`

Conectar remoto GitHub:

```bash
git remote add origin git@github.com:ORG_OR_USER/dmac-market-brief-agent.git
git push -u origin main
```

No se realiza push automatico desde este proyecto.

## Roadmap

- [x] Integracion BCCh API (TPM, IPC).
- [x] Scraping de fuente chilena activa (La Tercera Pulso).
- [x] RSS feeds depurados (5 fuentes funcionales).
- [x] Configuracion ruff y pytest.
- [ ] Integracion mindicador.cl (indicadores secundarios).
- [x] Agregar retry logic y circuit breaker a fuentes externas.
- [ ] Calendario economico con proveedor estable.
- [x] yfinance: series de 1 mes y sparklines en el correo.
- [ ] Mejor deduplicacion semantica de noticias.
- [ ] PostgreSQL opcional para despliegue compartido.
- [x] CI con pytest y ruff (`.github/workflows/ci.yml`).
- [ ] Panel web simple de auditoria historica.

## Notas De Riesgo

- yfinance es suficiente para prototipo, no para datos oficiales definitivos.
- Algunas fuentes RSS pueden cambiar o fallar.
- Las alertas son preliminares y no constituyen recomendacion de inversion.
- El sistema debe separar hechos observados de interpretacion financiera.
