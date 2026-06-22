# Deploy a produccion (servidor 24/7)

Guia paso a paso para desplegar `dmac-market-brief-agent` en un servidor Linux
remoto usando SSH + rsync + systemd + Docker.

## Prerequisitos

- Servidor Linux con Docker Engine + docker compose plugin
  (`docker --version` y `docker compose version`)
- Acceso SSH con un usuario que pueda usar `sudo`
- Credenciales de produccion listas:
  - `OLLAMA_API_KEY` (cuenta Ollama Cloud)
  - `SMTP_PASSWORD` (Gmail app password, 16 caracteres)
  - `EMAIL_TO` (destinatario final, ej. `brcarom@udd.cl`)
- (Opcional) `BCENTRAL_CREDENTIALS_FILE` si tienes cuenta del Banco Central

## Paso 1: Preparar el bundle local

Desde tu maquina de desarrollo, limpia archivos que NO deben ir al servidor:

```bash
cd /home/brunoc/dev/dmac/Agentes_de_Coyuntura
rm -rf outputs/* logs/* storage/*.db .ruff_cache .pytest_cache
find . -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null
find . -name "*.pyc" -delete
```

## Paso 2: Crear el directorio en el servidor

Conectate por SSH y crea el path donde vivira la app:

```bash
ssh usuario@servidor
sudo mkdir -p /opt/dmac-market-brief-agent
sudo chown usuario:usuario /opt/dmac-market-brief-agent
exit
```

## Paso 3: Subir archivos via rsync

Desde tu maquina local:

```bash
cd /home/brunoc/dev/dmac/Agentes_de_Coyuntura
rsync -avz --delete \
  --exclude='.venv' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  --exclude='.ruff_cache' \
  --exclude='outputs' \
  --exclude='storage/*.db' \
  --exclude='.git' \
  ./ usuario@servidor:/opt/dmac-market-brief-agent/
```

`rsync` re-instala dependencias (Docker las maneja) y copia el codigo fuente
+ archivos de configuracion. La primera vez tarda ~1 min.

## Paso 4: Configurar `.env` y credenciales

Conectate por SSH y configura el entorno:

```bash
ssh usuario@servidor
cd /opt/dmac-market-brief-agent
cp .env.production.example .env
nano .env
```

Llenar como minimo:

```ini
APP_ENV=production
TZ=America/Santiago
DRY_RUN=false
EMAIL_ENABLED=true
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=nix.assistant.bruno@gmail.com
SMTP_PASSWORD=<gmail app password>
EMAIL_FROM=nix.assistant.bruno@gmail.com
EMAIL_TO=brcarom@udd.cl
AI_ENABLED=true
AI_BRIEF_ENABLED=true
AI_CHARTS_ENABLED=true
OLLAMA_API_KEY=<real key>
OLLAMA_MODEL=gpt-oss:120b
OLLAMA_TIMEOUT_SECONDS=60
```

Si tienes credenciales BCCh (Banco Central), crea el archivo:

```bash
mkdir -p credentials
printf 'usuario_bcentral\npassword_bcentral\n' > credentials/bcentral.txt
chmod 600 credentials/bcentral.txt
```

Permisos criticos:

```bash
chmod 600 .env
chmod 700 credentials
```

## Paso 5: Instalar el servicio systemd

El script `deploy/install_server.sh` registra un servicio systemd que mantiene
`docker compose up -d` corriendo. Si el server rebootea, systemd lo levanta
automaticamente.

```bash
sudo ./deploy/install_server.sh
```

El script:

1. Copia `deploy/systemd/dmac-market-brief-agent.service` a `/etc/systemd/system/`
2. Adapta el `WorkingDirectory` al path real
3. `systemctl daemon-reload`
4. `systemctl enable --now dmac-market-brief-agent`
5. Ejecuta `docker compose up -d` (rebuild si hay cambios en codigo)

## Paso 6: Verificar el deploy

Estado del servicio systemd:

```bash
systemctl status dmac-market-brief-agent
```

Logs en vivo (combinados systemd + docker):

```bash
journalctl -u dmac-market-brief-agent -f
docker compose -f /opt/dmac-market-brief-agent/docker-compose.yml logs -f
```

Estado del container:

```bash
docker compose ps
```

## Paso 7: Smoke test

Corre el job manualmente para validar el flujo end-to-end (tarda 3-5 min):

```bash
docker compose exec dmac-market-brief-agent python -m app.main morning
```

Verifica que:

- Logs muestran "Email sent successfully" con el destinatario correcto
- El email llega a `brcarom@udd.cl` con la card IA al inicio
- Las visualizaciones estaticas (asset table, bars, distribucion) se ven OK
- NO hay bloque "Visualizaciones DMAC AI" con graficos IA (es MVP)

## Schedule automatico

APScheduler dentro del container corre (America/Santiago):

- **morning_brief**: lunes a viernes 08:30
- **market_close**: lunes a viernes 18:30
- **high_impact_monitor**: cada 15 minutos (revisa noticias de alto impacto
  y envia alerta si corresponde)

## Troubleshooting

### El email no llega

1. Verifica `journalctl -u dmac-market-brief-agent -n 100`
2. Confirma `DRY_RUN=false` en `.env`
3. Verifica que `SMTP_PASSWORD` es el Gmail app password (no la clave normal)
4. Comprueba conectividad: `docker compose exec dmac-market-brief-agent \
   python -c "import smtplib; s=smtplib.SMTP('smtp.gmail.com',587); s.starttls(); print('ok')"`

### Ollama falla

1. `gpt-oss:120b` tarda 30-60s por llamada. Si Ollama Cloud esta lento o caido,
   el brief usa el fallback deterministico (secciones de `summarizer.py`)
2. Verifica el API key: `docker compose exec dmac-market-brief-agent \
   python -c "import httpx; r=httpx.get('https://ollama.com', timeout=10); print(r.status_code)"`

### El container no arranca

```bash
docker compose logs dmac-market-brief-agent
```

Busca errores de import, sintaxis, o paths.

### Quiero ver el HTML generado sin enviar

Cambia `DRY_RUN=true` en `.env` y corre el job. El HTML queda en
`outputs/briefs/morning_brief_YYYYMMDD_HHMMSS.html`. Abrelo con un browser
para previsualizar.

## Actualizar el codigo en el futuro

```bash
# Local
git add -A && git commit -m "..." && git push

# Servidor
ssh usuario@servidor
cd /opt/dmac-market-brief-agent
rsync -avz --delete \
  --exclude='.venv' --exclude='__pycache__' \
  --exclude='.pytest_cache' --exclude='.ruff_cache' \
  --exclude='outputs' --exclude='storage/*.db' \
  --exclude='.git' \
  usuario@<server>:/opt/dmac-market-brief-agent/  # o git pull
sudo systemctl restart dmac-market-brief-agent
# Docker rebuilda automaticamente si hubo cambios en Dockerfile/requirements.txt
```

## Persistencia y backups

- **DB SQLite**: `storage/dmac_market_brief.db` registra todos los briefs
  enviados, snapshots de mercado y noticias. Recomendado: backup diario via
  cron o rsync a otro lugar.
- **Outputs**: `outputs/briefs/*.html` y `outputs/briefs/*.txt` por cada
  corrida. Sirven como auditoria y referencia. Pueden limpiarse despues de
  confirmar el envio.
- **Logs**: `logs/*.log` rotar con logrotate o limpiar mensualmente.

## Configuracion de horario personalizada

Si necesitas cambiar el horario (ej. sabados incluidos, otra hora), edita
`app/scheduler.py` y redespliega:

```python
scheduler.add_job(run_morning_brief, "cron", day_of_week="mon-sat", hour=8, minute=30, id="morning_brief")
scheduler.add_job(run_market_close, "cron", day_of_week="mon-sat", hour=18, minute=30, id="market_close")
```

## Comandos utiles

```bash
# Ver ultimos 50 logs
journalctl -u dmac-market-brief-agent -n 50

# Forzar una corrida del morning brief
docker compose exec dmac-market-brief-agent python -m app.main morning

# Inspeccionar la DB SQLite
docker compose exec dmac-market-brief-agent sqlite3 storage/dmac_market_brief.db ".tables"

# Reiniciar el servicio
sudo systemctl restart dmac-market-brief-agent

# Detener el servicio
sudo systemctl stop dmac-market-brief-agent

# Ver tamaño de la DB y outputs
du -sh /opt/dmac-market-brief-agent/storage/ /opt/dmac-market-brief-agent/outputs/
```
