# Handoff: sesion 2026-09-29 (cierre de la tarde)

Estado completo para retomar el trabajo en otra sesion. Detalle de cambios
en `CHANGELOG.md` ("Unreleased") y backlog tecnico en `NEXT_STEPS.md`.
Claude tiene prohibido hacer push: el merge y el push los hace el usuario.

## Estado de ramas y produccion (lo primero a revisar)

| Donde | Commit | Contenido |
|---|---|---|
| `origin/main` (y `main` local) | `925bddc` | Todo hasta relevancia chilena (salud de fuentes, CI, cupo Chile) |
| `chore/deploy-script` (local, sin push) | `457cef7` | `scripts/deploy.sh` + `DEPLOY.md` corregido |
| `fix/email-crossplatform` (local, sin push) | rama sobre `chore/deploy-script` | Correo multiplataforma (logo por URL, movil, sin rgba) + este handoff |
| **Produccion (`nixbox`)** | `163d8dc` (`DEPLOYED_COMMIT`) | = `fix/email-crossplatform` antes de este handoff |

**Produccion corre codigo que aun no esta en `origin/main`.** Integrar con
un solo fast-forward (incluye el script de deploy):

```bash
git checkout main && git merge --ff-only fix/email-crossplatform && git push origin main
```

## Servidor de produccion

- `bruno@nixbox` por Tailscale; app en `/opt/dmac-market-brief-agent`
  (Docker Compose). **No es repo git**: `git pull` ahi no hace nada.
- Desplegar SIEMPRE con `scripts/deploy.sh` (simulacion) y
  `scripts/deploy.sh --apply` (respaldo en `~/backups`, rsync seguro,
  rebuild, verificacion). `DEPLOY_REF=<rama>` para desplegar otra rama.
- Acceso de Claude: llave `~/.ssh/id_ed25519` (con passphrase) autorizada en
  el servidor. En cada sesion el usuario la desbloquea en un agente temporal:
  `ssh-agent -a /run/user/1000/ssh-claude.sock -t 8h` y
  `SSH_AUTH_SOCK=/run/user/1000/ssh-claude.sock ssh-add ~/.ssh/id_ed25519`.
- `.env` de produccion: `EMAIL_ENABLED=true`, `DRY_RUN=false`, IA activa
  (`AI_ENABLED`, `AI_BRIEF_ENABLED`, `AI_DRY_RUN=false`),
  `OPS_EMAIL_TO=brcarom@udd.cl`, monitor de alto impacto apagado.
  **Nunca correr `app.main morning/close` como prueba: envia a la lista.**
  Para probar, enviar a un solo destinatario con
  `EmailSender.send(..., recipients=[...])` sin guardar menciones (asi se
  hizo el correo "[PRUEBA]" del 2026-09-29 11:50).
- Respaldos en el servidor: `~/backups/dmac-20260929-pre-v0.14.tgz` (codigo
  de junio) y `~/backups/dmac-20260929-114708.tgz`.

## Que se hizo hoy (2026-09-29)

1. **Manana**: clasificador con limites de palabra; Diario Financiero;
   BCCh desempleo y USD/PEN; lectura de Nix por grafico "En foco".
2. **Salud de fuentes**: chequeo por corrida con histeresis, tablas
   `source_health`/`source_state`, `python -m app.main health`, aviso a
   `OPS_EMAIL_TO`, ultimo dato valido rotulado "al DD-MM", linea "Sin datos
   en esta edicion", CI en GitHub Actions, `requirements-dev.txt`.
3. **Relevancia chilena**: cupo 1 de 3 para Chile (solo si pasa calidad),
   region por defecto "Chile" en medios chilenos (salvo DF Internacional),
   filtro de comunicados administrativos de la Fed/BCE, DF con tier 2.
4. **Despliegue**: produccion corria el codigo de **junio** (0.1.0, yfinance
   0.2.48). Se desplego todo; incidente de ~2 min por excluir `storage/`
   completo en el rsync (tiene codigo), sin envios perdidos. Nacio
   `scripts/deploy.sh` y se corrigio el rsync de `DEPLOY.md`, que habria
   borrado `.env` y credenciales.
5. **Correo multiplataforma** (el usuario mostro el logo roto en Outlook PC):
   logo por URL HTTPS sobre recuadro blanco (Gmail/Outlook web no muestran
   `data:`), tabla de activos sin scroll horizontal desde ~340 px (antes
   minimo 436 px), sin `rgba()`, 72 -> 47 KB.

## Verificado en produccion

- yfinance 1.7.0: 17/17. BCCh: TPM 4.5, IPC 0.6, desempleo 9.53, USD/PEN
  3.44 con 22 dias. DF 17 y La Tercera 20 notas. 28/28 fuentes ok.
- Correo "[PRUEBA]" enviado solo a brcarom@udd.cl: Nix OK, 3 lecturas de
  "En foco" con lenguaje prudente, 1 titular chileno, 57.9 KB.
- Local: 321 tests, `ruff` limpio; capturas Chromium en 1200 px, 360 px
  (iframe; Chromium headless no baja de 500 px de ventana) y modo oscuro.

## Decisiones del usuario (no re-discutir sin motivo)

- Seleccion "En foco" deterministica; la IA solo redacta la linea.
- USD/PEN y desempleo desde el BCCh. DF como segunda fuente chilena (sin
  Opinion).
- `OPS_EMAIL_TO=brcarom@udd.cl`. Linea al lector con fuentes sin datos: si.
  Ultimo dato valido rotulado con fecha: si; la IA nunca lo recibe.
- Cupo chileno 1 de 3 y filtro de comunicados administrativos: si.
- Graficos del correo en HTML/CSS (sin imagenes); logo por URL.

## Trabajo pendiente (en orden sugerido)

1. **Integrar ramas** (usuario): fast-forward de arriba y push. El CI corre
   por primera vez en ese push; revisar la pestana Actions.
2. **Revisar el correo "[PRUEBA]"** en Outlook PC (con y sin "Mostrar
   contenido bloqueado"), Outlook/Gmail en telefono y Gmail web. Ajustar lo
   que se vea mal; Chromium no reproduce los motores de Outlook/Gmail.
3. **Revisar el cierre de las 18:30 del 2026-09-29** (primer envio real con
   todo lo nuevo): `docker compose logs --since 1h dmac-market-brief-agent`
   y `python -m app.main health` en el servidor.
4. **Brent -8.46% en el dia con +6.5% en el mes** (29-09): probable cambio
   de contrato de `BZ=F` a fin de mes en Yahoo. Investigar; si se confirma,
   evaluar marcar o suavizar la variacion en dias de roll (tambien `CL=F`,
   `HG=F`, `GC=F`). La salud de fuentes no lo detecta (umbral 25%).
5. **Router de temas IA intermitente**: respuesta vacia para "Estados
   Unidos" (`Strict JSON parse failed ... char 0`); el pipeline sigue sin ese
   bloque. Ver reintento o `AI_STRICT_JSON`.
6. **Calidad de noticias** (`services/news_quality.py`): `HIGH_SIGNAL_TERMS`
   y `LOW_VALUE_PATTERNS` aun por substring e incluyen el nombre de la fuente
   ("federal reserve" siempre es alta senal). `impact_scoring` suma +1 a
   Latam/EE.UU./Global pero no a Chile (confirmar si es intencional).
7. **Salud de fuentes**: calibrar umbrales tras ~2 semanas mirando `health`.
8. **Correo**: 320 px aun desborda ~22 px; simbolo redundante bajo el nombre
   ("IPSA / IPSA"); considerar `color-scheme` para modo oscuro.
9. Backlog de `NEXT_STEPS.md`: IPSA oficial (BCCh), `^TNX` en puntos base,
   GET condicional, monitor mas liviano, deduplicacion O(n^2), paso (b) de
   IA en "En foco", proteger `main` exigiendo CI verde.

## Entorno local

`mise exec python@3.11 -- python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt`
y `.venv/bin/python -m pytest -q`. Preview del correo sin enviar: ver
`collect_market_and_news_with_health` + `build_email_html` (no hay `.env`
local: sin credenciales BCCh, esas 4 fuentes salen "sin datos").
