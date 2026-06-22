# Changelog

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
- Morning brief enviado por SMTP a `brcarom@udd.cl`: card IA al inicio,
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
