# dmac-market-brief-agent

Agente de coyuntura financiera para el Data Market Analysis Club UDD. El proyecto recolecta datos de mercado, titulares economicos y eventos relevantes para generar Morning Brief, Market Close, alertas de alto impacto, correos automaticos y versiones cortas listas para copiar en WhatsApp.

El MVP prioriza simpleza, bajo costo, auditoria y mantenibilidad por estudiantes.

## Funcionalidades

- Morning Brief diario con texto, HTML y WhatsApp.
- Market Close diario con movimientos relevantes y posibles drivers.
- Monitor de alertas de alto impacto financiero.
- Persistencia auditable en SQLite.
- Envio SMTP opcional con `DRY_RUN` por defecto.
- Tolerancia a fallas de APIs externas.
- Scheduler interno con APScheduler.
- Docker y Docker Compose.

## Arquitectura

- `app/`: CLI, configuracion, logging y scheduler.
- `data_sources/`: conectores externos como yfinance, RSS, BCCh, FRED y Alpha Vantage.
- `services/`: logica de negocio, scoring, clasificacion, formatos y email.
- `jobs/`: Morning Brief, Market Close y monitor de alertas.
- `storage/`: SQLite, modelos y repositorios.
- `prompts/`: guias editoriales para futuras integraciones con LLM.
- `outputs/`: briefs, alertas y mensajes WhatsApp generados.
- `tests/`: tests unitarios sin llamadas externas.

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
```

Los archivos se guardan en:

- `outputs/briefs/`
- `outputs/alerts/`
- `outputs/whatsapp/`

## Docker

```bash
cp .env.example .env
docker compose build
docker compose up -d
```

El contenedor ejecuta `python -m app.main scheduler` por defecto y monta:

- `./outputs:/app/outputs`
- `./logs:/app/logs`
- `./storage:/app/storage`

Validar configuracion:

```bash
docker compose config
```

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

- Integracion real con Banco Central de Chile.
- Integracion FRED y Alpha Vantage.
- Calendario economico con proveedor estable.
- PostgreSQL opcional para despliegue compartido.
- Mejor deduplicacion semantica de noticias.
- Plantillas editoriales revisadas por el equipo DMAC.
- Panel web simple de auditoria historica.
- CI con pytest y ruff.

## Notas De Riesgo

- yfinance es suficiente para prototipo, no para datos oficiales definitivos.
- Algunas fuentes RSS pueden cambiar o fallar.
- Las alertas son preliminares y no constituyen recomendacion de inversion.
- El sistema debe separar hechos observados de interpretacion financiera.
