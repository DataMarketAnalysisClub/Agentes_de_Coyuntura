# Handoff: sesion 2026-09-30 (cierre)

Estado completo para retomar el trabajo en otra sesion. Detalle de cambios
en `CHANGELOG.md` ("Unreleased") y backlog tecnico en `NEXT_STEPS.md`.
Claude no hace commits ni push (desde el 2026-09-29): deja los cambios sin
commitear y entrega los commits propuestos; el usuario los hace junto al push.
Como `scripts/deploy.sh` despliega solo codigo commiteado, antes de desplegar
cambios nuevos el usuario debe commitearlos.

## Siguiente mision: auditoria completa de seguridad

Desde el 2026-09-30 el proyecto tiene una superficie publica en internet (el
servicio de suscripcion via Tailscale Funnel) y una base con datos
personales. Antes de encender el envio a suscriptores, auditar de punta a
punta. Alcance minimo:

1. **Servicio publico** (`app/subscription_server.py`): `http.server` de la
   libreria estandar expuesto a internet. Revisar DoS (`ThreadingHTTPServer`
   sin tope de hilos; hoy solo `timeout = 15` y cuerpos <= 4 KB), abuso del
   formulario (topes de confirmacion por correo y por hora; sin limite por
   IP), cabeceras (CSP, HSTS lo pone Funnel?), manejo de errores sin fugas,
   tokens en URLs (Referrer-Policy, logs propios y de `tailscaled`/Funnel).
   Evaluar un proxy delante (Caddy/nginx con rate limit) o endurecer.
2. **Datos personales**: MySQL (usuario de app con permisos minimos?, root
   solo para dumps), respaldos en `~/backups` sin cifrar (tar con `.env`,
   SQLite y dumps de suscriptores), retencion de `pending` vencidos,
   `subscribers erase`, politica de privacidad (ley 19.628 / 21.719).
3. **Secretos**: `.env` de produccion (permisos 600), app password de Gmail,
   `OLLAMA_API_KEY`, credenciales BCCh. **Rotar la contrasena del BCCh**: el
   2026-09-30 un `docker compose config` sin `--no-interpolate` imprimio el
   `.env` local en la salida de la sesion de Claude (no salio a terceros).
   Buscar secretos en el historial de git.
4. **Servidor `nixbox`**: puertos escuchando en todas las interfaces (22, 53,
   80, 3000, 8080 = nginx por defecto de otro uso, 11434 = Ollama, 25566,
   25575); `bruno` con `sudo` sin contrasena y en el grupo `docker`;
   actualizaciones del SO; el contenedor de la app corre como root.
5. **Tailscale**: la politica permite todo entre dispositivos (`grants`
   `*`->`*`); Funnel habilitado para `autogroup:member`. Acotar Funnel a
   `nixbox` (tag) y revisar quien esta en el tailnet.
6. **Dependencias**: `pip-audit` sobre `requirements.txt`, imagen base
   `python:3.11-slim` y `mysql:8.4`.
7. **Correo**: SPF/DKIM/DMARC del remitente (Gmail personal hoy; SMTP UDD a
   futuro), cabeceras `List-Unsubscribe`, que ningun envio exponga la lista.

## Despues: frontend de las paginas de suscripcion

Las paginas que sirve el servicio (`/`, `/confirmar`, `/baja` y sus
mensajes, en `app/subscription_server.py`) son sobrias y sin logo. Mejorarlas
con la identidad del brief: logo DMAC, tipografia y colores del diseno
"Editorial". Ojo: la CSP actual es `default-src 'none'` (bloquea imagenes);
servir el logo desde el propio servicio (ruta `/logo.png` +
`img-src 'self'`) o como `data:` (`img-src data:`). Revisar tambien los
correos de confirmacion y bienvenida (`services/subscriptions.py`), que hoy
no llevan logo.

## Estado de ramas y produccion (lo primero a revisar)

| Donde | Commit | Contenido |
|---|---|---|
| `origin/main` | `33a0a67` | Mailing completo, bienvenida, "Suscribete" en el pie, limpieza de Nix |
| `main` local | ver `git log` | + este handoff y docs de la activacion (commit propuesto) |
| **Produccion (`nixbox`)** | `33a0a67` | Desplegado el 2026-09-30 21:28 (respaldo `~/backups/dmac-20260930-212820.tgz`) |

Comprobar con `git log --oneline origin/main..main` que falta pushear y con
`ssh bruno@nixbox cat /opt/dmac-market-brief-agent/DEPLOYED_COMMIT` que
corre produccion.

## Servidor de produccion

- `bruno@nixbox` por Tailscale; app en `/opt/dmac-market-brief-agent`
  (Docker Compose). **No es repo git**: `git pull` ahi no hace nada.
- Desplegar SIEMPRE con `scripts/deploy.sh` (simulacion) y
  `scripts/deploy.sh --apply` (respaldo en `~/backups`, `mysqldump` si
  `mysql` corre, rsync seguro, rebuild, verificacion). El usuario autorizo a
  Claude a desplegar (2026-09-29).
- Acceso de Claude: llave `~/.ssh/id_ed25519` (con passphrase). En cada
  sesion el usuario la desbloquea en un agente temporal (8 h):
  `ssh-agent -a /run/user/1000/ssh-claude.sock -t 8h` y
  `SSH_AUTH_SOCK=/run/user/1000/ssh-claude.sock ssh-add ~/.ssh/id_ed25519`.
- Contenedores: `dmac-market-brief-agent` (scheduler), `dmac-mysql`
  (volumen `mysql-data`, sin puertos) y `dmac-subscriptions`
  (`127.0.0.1:8090`). Los dos ultimos por `COMPOSE_PROFILES=mailing`.
- `.env` de produccion: `EMAIL_ENABLED=true`, `DRY_RUN=false`, IA activa,
  `EMAIL_TO=dmac@udd.cl`, `OPS_EMAIL_TO=dmac@udd.cl`, monitor de alto
  impacto apagado, y desde el 2026-09-30: `COMPOSE_PROFILES=mailing`,
  `MAILING_ENABLED=false`, `MAILING_PUBLIC_URL=https://nixbox.tailce797f.ts.net`,
  `MAILING_HOST_PORT=8090` (el 8080 es de un nginx del sistema) y
  `MYSQL_PASSWORD`/`MYSQL_ROOT_PASSWORD` generadas en el servidor (nunca se
  imprimieron). Respaldos del `.env`: `~/backups/env-20261001-002913.bak`
  (antes del mailing) y `~/backups/env-20260929-182440.bak`.
  **Nunca correr `app.main morning/close` como prueba: envia a la lista.**
- **Funnel**: `https://nixbox.tailce797f.ts.net` -> `127.0.0.1:8090`
  (`sudo tailscale funnel --bg 8090`; apagar con
  `sudo tailscale funnel --https=443 off`). El DNS publico tardo mas de 20 min en
  aparecer la primera vez (bug conocido de Tailscale con 1.102.2,
  issues #21502/#21429): si un celular no encuentra el servidor, consultar
  `dig @ns1.dnsimple.com nixbox.tailce797f.ts.net A`; desde un equipo con
  Tailscale el nombre resuelve siempre (MagicDNS) y no prueba nada.
  Verificado desde internet el 2026-09-30: `/` 200, `/salud` 200.
- **Suscriptores** (2026-09-30): 1 `active` (brcarom@udd.cl, alta de
  prueba) y 2 `pending` (pruebas del usuario). `dmac@udd.cl` aun no esta
  sembrado. Ver con
  `docker compose exec -T dmac-subscriptions python -m app.main subscribers list`.
- **Correo de prueba con links reales**: script que da de alta al
  destinatario con `subscribers add`, replica `jobs.market_close` sin
  guardar brief/menciones/salud, suprime avisos a mantenedores y envia por
  `EmailSender.send` con el mailing encendido solo en ese proceso y una
  lista de un unico suscriptor. Se ejecuta con
  `ssh bruno@nixbox "cd /opt/dmac-market-brief-agent && docker compose exec -T dmac-market-brief-agent python -" < script.py`.
  El clasificador de permisos de Claude bloquea ese envio ("Remote Shell
  Writes"): Claude prepara el script y el usuario lo corre con `!`.

## Entorno local

- `.env` local (copiado de `.env.example`, permisos 600, ignorado por git)
  con credenciales del BCCh **solo en esta maquina**; `DRY_RUN=true`,
  `EMAIL_ENABLED=false`, IA apagada. Nunca imprimir su contenido: usar
  `docker compose config --no-interpolate`.
- Sin Docker utilizable ni MySQL en la maquina de desarrollo: los tests del
  repositorio de suscriptores corren el SQL sobre SQLite (`tests/conftest.py`).
- `mise exec python@3.11 -- python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`;
  `.venv/bin/python -m pytest -q` (408 tests) y `.venv/bin/ruff check .`.

## Que se hizo el 2026-09-30

1. **Mailing con suscripcion** (decision: servicio web propio + Tailscale
   Funnel, no formularios externos): MySQL 8.4 con `subscribers` y
   `subscriber_events`; `app/subscription_server.py` con formulario, doble
   confirmacion, baja por link y de un clic (RFC 8058), confirmar/bajar
   solo por POST; `EmailSender` envia un correo por suscriptor activo con
   link de baja y `List-Unsubscribe` (si MySQL falla, va a `EMAIL_TO`); CLI
   `subscribers count|list|add|remove|erase`; perfil `mailing` en compose;
   `mysqldump` en `deploy.sh`. DDL verificado contra un MySQL 8.4 desechable.
2. **Bienvenida e invitacion**: correo de bienvenida al confirmar; pie del
   brief con "¿Te reenviaron este correo? Suscribete a DMAC Brief".
3. **Nix**: `services/ai/editorial_polish.py` cambia codigos internos
   ("USDCLP", "US30Y", "COPPER") por nombres legibles en el titular/asunto y
   todo el texto, y corrige prefijos "Posible que" -> "Es posible que".
4. **Produccion**: desplegado `6b088ce` y luego `33a0a67`; infraestructura
   del mailing y Funnel activos, envio a suscriptores aun apagado. Envios
   reales del 29 (cierre) y 30 (manana y cierre) `sent`, fuentes `ok`.
5. **Pruebas del usuario**: correo de prueba con links reales a
   brcarom@udd.cl; links funcionan desde el PC y, tras aparecer el DNS
   publico, desde celulares.

## Decisiones del usuario (no re-discutir sin motivo)

- Seleccion "En foco" deterministica; la IA solo redacta la linea.
- USD/PEN y desempleo desde el BCCh. DF como segunda fuente chilena (sin
  Opinion).
- Destinatario del brief y de los avisos de operacion: `dmac@udd.cl`
  (`EMAIL_TO` y `OPS_EMAIL_TO`). Tras editar el `.env` de produccion:
  respaldarlo antes y recrear el contenedor
  (`docker compose up -d --force-recreate`) para que lo lea.
- Linea al lector con fuentes sin datos: si.
  Ultimo dato valido rotulado con fecha: si; la IA nunca lo recibe.
- Cupo chileno 1 de 3 y filtro de comunicados administrativos: si.
- Graficos del correo en HTML/CSS (sin imagenes).
- Diseno "Editorial" (propuesta A) aprobado; debe ser responsivo.
- USD/CLP de Yahoo en la tabla + dolar observado del BCCh como referencia.
- Asunto con el titular de Nix ("DMAC Brief · 29 sep — <titular>").
- Correo solo claro (sin paleta oscura propia) y logo embebido.
- SMTP institucional de la UDD: el usuario lo pedira cuando el brief sea
  algo demostrable y en uso; por ahora sigue la cuenta Gmail.
- IPSA desde yfinance con `MXIPSAGC.SN`. No buscar otra fuente salvo que
  Yahoo deje de publicarlo.
- Mailing: servicio web propio publicado con Tailscale Funnel, con doble
  confirmacion y baja de un clic. No usar formularios externos.
- Suscripcion: abierta a cualquier correo (no solo `@udd.cl`), solo se pide
  el correo, ambas ediciones siempre, correo de bienvenida al confirmar e
  invitacion "¿Te reenviaron este correo?" en el pie del brief.
- Dominio propio: `dmac.cl` estaba libre en NIC Chile el 2026-09-30 (CLP
  9.990/ano). El usuario evaluara una pagina web del club; si se compra,
  Cloudflare (DNS + Tunnel) seria la alternativa a Funnel. Titular del
  dominio: idealmente el club/UDD, no una persona.

## Trabajo pendiente (en orden sugerido)

1. **Auditoria de seguridad** (ver arriba). Bloquea encender el envio.
2. **Frontend de las paginas de suscripcion** con logo (ver arriba).
3. **Encender el mailing**: sembrar `subscribers add dmac@udd.cl`, decidir
   si brcarom@udd.cl sigue en la lista, `MAILING_ENABLED=true` y
   `docker compose up -d --force-recreate`. DEPLOY.md, paso 5.
4. **Remitente institucional**: el correo sale de una cuenta Gmail
   personal (~500 destinatarios/dia; cada suscriptor recibe 2). Pasar al
   SMTP de la UDD antes de ~200 suscriptores.
5. **Router de temas IA intermitente**: respuesta vacia para "Estados
   Unidos" (`Strict JSON parse failed ... char 0`).
6. **Calidad de noticias** (`services/news_quality.py`): `HIGH_SIGNAL_TERMS`
   y `LOW_VALUE_PATTERNS` por substring e incluyen el nombre de la fuente;
   `impact_scoring` no suma +1 a Chile.
7. **Nix**: revisar en correos reales si quedan hechos copiados en ingles
   (solo lo pide el prompt). El asunto del 30-09 decia "Treasury 10Y" (es
   el `name` del activo, no un codigo).
8. **Salud de fuentes**: calibrar umbrales tras ~2 semanas mirando `health`.
9. Backlog de `NEXT_STEPS.md`: GET condicional, monitor mas liviano,
   deduplicacion O(n^2), paso (b) de IA en "En foco", proteger `main`
   exigiendo CI verde.
