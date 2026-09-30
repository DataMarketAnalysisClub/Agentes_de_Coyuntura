# Handoff: sesion 2026-09-30

Estado completo para retomar el trabajo en otra sesion. Detalle de cambios
en `CHANGELOG.md` ("Unreleased") y backlog tecnico en `NEXT_STEPS.md`.
Claude no hace commits ni push (desde el 2026-09-29): deja los cambios sin
commitear y entrega los commits propuestos; el usuario los hace junto al push.
Como `scripts/deploy.sh` despliega solo codigo commiteado, antes de desplegar
cambios nuevos el usuario debe commitearlos.

## Estado de ramas y produccion (lo primero a revisar)

| Donde | Commit | Contenido |
|---|---|---|
| `origin/main` | `239704e` | Brent (contrato vigente), diseno Editorial, series BCCh, decision IPSA |
| `main` local | ver `git log` | + modo oscuro, textos mas grandes en telefono y este handoff (sin push) |
| **Produccion (`nixbox`)** | ver `DEPLOYED_COMMIT` en el servidor | Se despliega `main` local con `scripts/deploy.sh` |

Comprobar con `git log --oneline origin/main..main` que falta pushear y con
`ssh bruno@nixbox cat /opt/dmac-market-brief-agent/DEPLOYED_COMMIT` que
corre produccion.

## Servidor de produccion

- `bruno@nixbox` por Tailscale; app en `/opt/dmac-market-brief-agent`
  (Docker Compose). **No es repo git**: `git pull` ahi no hace nada.
- Desplegar SIEMPRE con `scripts/deploy.sh` (simulacion) y
  `scripts/deploy.sh --apply` (respaldo en `~/backups`, rsync seguro,
  rebuild, verificacion). `DEPLOY_REF=<rama|commit>` para otra referencia.
  El usuario autorizo a Claude a desplegar (2026-09-29).
- Acceso de Claude: llave `~/.ssh/id_ed25519` (con passphrase). En cada
  sesion el usuario la desbloquea en un agente temporal:
  `ssh-agent -a /run/user/1000/ssh-claude.sock -t 8h` y
  `SSH_AUTH_SOCK=/run/user/1000/ssh-claude.sock ssh-add ~/.ssh/id_ed25519`.
- `.env` de produccion: `EMAIL_ENABLED=true`, `DRY_RUN=false`, IA activa,
  `EMAIL_TO=dmac@udd.cl` y `OPS_EMAIL_TO=dmac@udd.cl` (desde el
  2026-09-29; antes brcarom@udd.cl, respaldo del `.env` en
  `~/backups/env-20260929-182440.bak`), monitor de alto impacto apagado. Las
  series nuevas del BCCh usan los defaults de `app/config.py` (no hace falta
  agregarlas al `.env`).
  **Nunca correr `app.main morning/close` como prueba: envia a la lista.**
- Correo de prueba: replicar el job con `EmailSender.send(...,
  recipients=["dmac@udd.cl"])`, sin `BriefRepository().save` ni
  `save_mentions`, ejecutando el script dentro del contenedor:
  `ssh bruno@nixbox "cd /opt/dmac-market-brief-agent && docker compose exec -T dmac-market-brief-agent python -" < script.py`.
- Respaldos: `~/backups/dmac-20260929-114708.tgz` (antes del correo
  multiplataforma) y `~/backups/dmac-20260929-144512.tgz` (antes de `239704e`).

## Entorno local

- `.env` local (copiado de `.env.example`, permisos 600, ignorado por git)
  con credenciales del BCCh **solo en esta maquina**; `DRY_RUN=true`,
  `EMAIL_ENABLED=false`, IA apagada. Nunca imprimir su contenido.
- Los tests ignoran el `.env` (fixture en `tests/conftest.py`).
- `mise exec python@3.11 -- python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`;
  `.venv/bin/python -m pytest -q` (403 tests) y `.venv/bin/ruff check .`.

## Que se hizo el 2026-09-30: mailing con suscripcion (sin activar)

Decision del usuario: servicio web propio + Tailscale Funnel (no Google o
Microsoft Forms). Implementado y apagado por defecto: sin
`COMPOSE_PROFILES=mailing` y `MAILING_ENABLED=true` produccion no cambia.

- MySQL 8.4 (contenedor `mysql`, volumen `mysql-data`) con `subscribers` y
  `subscriber_events` (`storage/subscribers.py`).
- `app/subscription_server.py` (`python -m app.main web`, contenedor
  `dmac-subscriptions` en `127.0.0.1:8080`): formulario, doble confirmacion,
  baja por link y de un clic (RFC 8058). Confirmar/bajar solo por POST.
- `EmailSender`: con mailing, un correo por suscriptor activo con link de
  baja y `List-Unsubscribe`; si MySQL falla, va a `EMAIL_TO`.
- CLI `python -m app.main subscribers count|list|add|remove|erase`.
- `scripts/deploy.sh` hace `mysqldump` a `~/backups` si `mysql` corre.
- 379 tests (43 nuevos). El DDL de MySQL no se probo en vivo (sin Docker ni
  MySQL en la maquina de desarrollo).
- Activacion paso a paso: DEPLOY.md, "Mailing con suscripcion".

## Que se hizo el 2026-09-29 (tarde)

1. **Brent -8%**: era el cambio de contrato de `BZ=F` (nov -> dic). El
   cliente de yfinance ahora usa el contrato vigente (`underlyingSymbol`)
   para todos los futuros `=F`; si Yahoo no responde, usa el continuo.
2. **Diseno "Editorial"** (propuesta A del canvas de Claude Design
   https://claude.ai/artifact/8FwBUAh8u3RYssbvkPodVJ): cabecera tipo
   periodico, "Lo esencial" de Nix (Chile primero), cifras clave, mercados
   agrupados, "En foco" en 2 columnas. Columnas fluidas que se apilan sin
   `@media` y tabla `<!--[if mso]>` para Outlook de escritorio. Formato
   chileno de numeros, Treasury en pb, tildes. `render_nix_editorial`
   reemplaza el HTML de Nix duplicado en los jobs.
3. **Modo oscuro y logo**: una paleta oscura propia fallo en Outlook nuevo
   (la aplicaba segun el tema de Windows aunque el lector eligiera "fondo
   claro", y encima convertia los colores). Se retiro: el correo es solo
   claro (blanco puro, texto casi negro) y cada cliente lo invierte. El logo
   va embebido (`cid:dmac-logo`, `assets/Dmac_logo_email.png` con fondo
   blanco dentro del PNG), el remitente tiene nombre ("DMAC Brief · Nix") y
   hay vista previa oculta con el titular de Nix. Textos chicos +1 px.
4. **BCCh**: dolar observado, UF y cobre BML (diarias, con historia); IPC 12
   meses e IMACEC; TPM/IPC/IMACEC/desempleo con periodo y cambio en pp.
   Codigos verificados con `SearchSeries` y documentados en el README.
5. **IPSA**: se evaluaron fuentes (README); el usuario aprobo `MXIPSAGC.SN`.

## Verificado

- Produccion con `239704e`: 17/17 yfinance, todas las series BCCh con dato,
  Brent -1,07%, correo "[PRUEBA]" enviado a brcarom@udd.cl (68 KB).
- Produccion con `3bc3087` (asunto con titular, logo embebido): correo
  "[PRUEBA]" recibido bien en `dmac@udd.cl` (69 KB), todas las fuentes ok.
- Local: capturas Chromium en 1200, 390 y 320 px. Solo
  claro el correo pesa ~68 KB (limite de recorte de Gmail ~102 KB).

## Decisiones del usuario (no re-discutir sin motivo)

- Seleccion "En foco" deterministica; la IA solo redacta la linea.
- USD/PEN y desempleo desde el BCCh. DF como segunda fuente chilena (sin
  Opinion).
- Destinatario del brief y de los avisos de operacion: `dmac@udd.cl`
  (`EMAIL_TO` y `OPS_EMAIL_TO`, cambio pedido por el usuario el 2026-09-29).
  Tras editar el `.env` de produccion: respaldarlo antes y recrear el
  contenedor (`docker compose up -d --force-recreate`) para que lo lea.
- Linea al lector con fuentes sin datos: si.
  Ultimo dato valido rotulado con fecha: si; la IA nunca lo recibe.
- Cupo chileno 1 de 3 y filtro de comunicados administrativos: si.
- Graficos del correo en HTML/CSS (sin imagenes); logo por URL.
- Diseno "Editorial" (propuesta A) aprobado; debe ser responsivo.
- USD/CLP de Yahoo en la tabla + dolar observado del BCCh como referencia.
- Asunto con el titular de Nix ("DMAC Brief · 29 sep — <titular>").
- Correo solo claro (sin paleta oscura propia) y logo embebido: el usuario
  valido las visuales en Outlook el 2026-09-29.
- SMTP institucional de la UDD: el usuario lo pedira cuando el brief sea
  algo demostrable y en uso; por ahora sigue la cuenta Gmail.
- IPSA desde yfinance con `MXIPSAGC.SN` (aprobado 2026-09-29). No buscar
  otra fuente salvo que Yahoo deje de publicarlo.
- Mailing: servicio web propio publicado con Tailscale Funnel, con doble
  confirmacion y baja de un clic (2026-09-30). No usar formularios externos.

## Trabajo pendiente (en orden sugerido)

1. **Revisar Gmail y el celular**: Outlook nuevo (claro y oscuro) ya fue
   validado por el usuario. Si el logo embebido falla en algun cliente,
   volver a URL con `EMAIL_LOGO_URL=https://...`.
2. **Revisar el cierre de las 18:30 del 2026-09-29** (primer envio real a
   `dmac@udd.cl` con todo lo nuevo): `docker compose logs --since 1h dmac-market-brief-agent`
   y `python -m app.main health` en el servidor.
3. **Remitente institucional**: el correo sale de una cuenta Gmail
   personal; Outlook UDD lo marca "remitente externo" y bloquea imagenes
   externas. Una casilla del club o de la UDD mejoraria la entrega.
4. **Router de temas IA intermitente**: respuesta vacia para "Estados
   Unidos" (`Strict JSON parse failed ... char 0`). Ver reintento o
   `AI_STRICT_JSON`.
5. **Calidad de noticias** (`services/news_quality.py`): `HIGH_SIGNAL_TERMS`
   y `LOW_VALUE_PATTERNS` por substring e incluyen el nombre de la fuente.
   `impact_scoring` suma +1 a Latam/EE.UU./Global pero no a Chile.
   La nota de DF del dolar quedo como region "EE.UU." en un envio anterior.
6. **Nix**: codigos ("USDCLP") y prefijos rotos corregidos el 2026-09-30
   (`services/ai/editorial_polish.py` + prompts). Falta mirar en correos
   reales si quedan hechos copiados en ingles (solo lo pide el prompt).
7. **Salud de fuentes**: calibrar umbrales tras ~2 semanas mirando `health`.
8. **Activar el mailing con suscripcion**: implementado el 2026-09-30,
   falta DEPLOY.md "Mailing con suscripcion" (pasos 1-5: `.env`, Funnel,
   prueba desde un telefono, `subscribers add dmac@udd.cl`, encender).
   Conviene junto con el SMTP institucional de la UDD. Pendientes en
   `NEXT_STEPS.md`.
9. Backlog de `NEXT_STEPS.md`: GET condicional, monitor mas liviano,
   deduplicacion O(n^2), paso (b) de IA en "En foco", proteger `main`
   exigiendo CI verde.
