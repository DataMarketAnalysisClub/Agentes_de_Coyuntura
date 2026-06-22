# dmac-market-brief-agent

Agente de coyuntura financiera para el Data Market Analysis Club UDD. El proyecto recolecta datos de mercado, titulares economicos y eventos relevantes para generar Morning Brief, Market Close, alertas de alto impacto, correos automaticos y versiones cortas listas para copiar en WhatsApp.

El MVP prioriza simpleza, bajo costo, auditoria y mantenibilidad por estudiantes.

## Funcionalidades

- Morning Brief diario con texto, HTML y WhatsApp.
- Market Close diario con movimientos relevantes y posibles drivers.
- Monitor de alertas de alto impacto financiero.
- Analisis editorial IA (Ollama Cloud) que reemplaza el resumen deterministico
  cuando esta disponible.
- Visualizaciones estaticas en el email (asset table, barras de variacion %,
  distribucion por region). Render JS-free, compatibles con todos los clientes.
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
- `outputs/`: briefs, alertas y mensajes WhatsApp generados.
- `tests/`: tests unitarios sin llamadas externas.

### Fuentes de Datos

**Datos economicos:**
- BCCh API: TPM, IPC (requiere credenciales)
- yfinance: precios de activos (USDCLP, COPPER, IPSA, SP500, etc.)

**Noticias RSS (5 fuentes funcionales):**
- Federal Reserve (EE.UU. macro)
- ECB (Eurozona)
- Financial Times (global)
- MarketWatch (mercados EE.UU.)
- Investing.com (forex, commodities)

**Noticias Chile (scraping):**
- Ministerio de Hacienda: comunicados de politica fiscal
- La Tercera Pulso: negocios y economia chilena

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
- `change_pct_bar`: variacion % de activos
- `impact_ranking_bar`: ranking de noticias por impacto
- `news_by_region_bar`: distribucion de noticias por region
- `news_by_topic_bar`: distribucion de noticias por topic
- `assets_table`: tabla de principales activos

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
1. `change_pct_bar` (variacion de activos)
2. `impact_ranking_bar` (noticias por impacto)
3. `assets_table` (tabla de activos)
4. `news_by_region_bar` / `news_by_topic_bar`

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
.venv/bin/python -m pip install -r requirements.txt
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

Banco Central de Chile:

- `BCENTRAL_USER`: usuario BCCh. Puede omitirse si se usa `BCENTRAL_CREDENTIALS_FILE`.
- `BCENTRAL_PASSWORD`: contrasena BCCh. Puede omitirse si se usa `BCENTRAL_CREDENTIALS_FILE`.
- `BCENTRAL_CREDENTIALS_FILE`: ruta a archivo externo no versionado. Formato esperado: primera linea correo, segunda linea contrasena.
- `BCENTRAL_TPM_SERIES`: serie para TPM. Default: `F022.TPM.TIN.D001.NO.Z.D`.
- `BCENTRAL_IPC_SERIES`: serie para IPC/inflacion. Default: `F074.IPC.VAR.Z.Z.C.M`.
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
- `outputs/whatsapp/`

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
docker compose config
```

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
- `SMTP_USER=nix.assistant.bruno@gmail.com`
- `SMTP_PASSWORD=<Gmail App Password>`
- `EMAIL_FROM=nix.assistant.bruno@gmail.com`
- `EMAIL_TO=brcarom@udd.cl`
- `BCENTRAL_CREDENTIALS_FILE=/app/credentials/bcentral.txt`
- `AI_ENABLED=true`
- `AI_DRY_RUN=false`
- `OLLAMA_API_KEY=<key>`

### Horarios Scheduler

- Morning brief: lunes a viernes 08:30 America/Santiago.
- Market close: lunes a viernes 18:30 America/Santiago.
- High impact monitor: cada 15 minutos.

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
3. Si debe aparecer en WhatsApp, agrega el simbolo en `WATCH_SYMBOLS`.
4. Agrega o ajusta tests.

## Activar Correo

1. Configura SMTP en `.env`.
2. Define `EMAIL_TO` y opcionalmente `EMAIL_CC` separados por coma.
3. Cambia `DRY_RUN=false`.
4. Cambia `EMAIL_ENABLED=true` para briefs.
5. Cambia `ALERT_EMAIL_ENABLED=true` para alertas.

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
- [x] Scraping de fuentes chilenas (Ministerio Hacienda, La Tercera Pulso).
- [x] RSS feeds depurados (5 fuentes funcionales).
- [x] Configuracion ruff y pytest.
- [ ] Integracion mindicador.cl (indicadores secundarios).
- [ ] Agregar retry logic y circuit breaker a fuentes externas.
- [ ] Calendario economico con proveedor estable.
- [ ] Mejor deduplicacion semantica de noticias.
- [ ] PostgreSQL opcional para despliegue compartido.
- [ ] CI con pytest y ruff.
- [ ] Panel web simple de auditoria historica.

## Notas De Riesgo

- yfinance es suficiente para prototipo, no para datos oficiales definitivos.
- Algunas fuentes RSS pueden cambiar o fallar.
- Las alertas son preliminares y no constituyen recomendacion de inversion.
- El sistema debe separar hechos observados de interpretacion financiera.
