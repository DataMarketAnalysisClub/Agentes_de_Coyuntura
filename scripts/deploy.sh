#!/usr/bin/env bash
# Despliega un ref de git (por defecto main) al servidor de produccion.
#
# Uso:
#   scripts/deploy.sh                  # simulacion: muestra que cambiaria
#   scripts/deploy.sh --apply          # respaldo + sync + rebuild + verificacion
#   DEPLOY_HOST=bruno@nixbox DEPLOY_REF=v0.15.0 scripts/deploy.sh --apply
#
# Que hace (con --apply):
#   1. Respaldo completo del directorio remoto en ~/backups (incluye .env,
#      base SQLite y credenciales; permisos 600).
#   2. rsync --delete desde `git archive <ref>`: solo codigo commiteado.
#      Nunca toca .env, storage/*.db, credentials/, outputs/ ni logs/.
#      Ojo: storage/ tiene codigo (repositories.py, models.py) ademas de la
#      base, por eso se excluye solo *.db y no la carpeta.
#   3. docker compose up -d --build y espera a que el contenedor este Up.
#   4. Verificacion: logs sin tracebacks y diagnostico de yfinance.
#
# Rollback: restaurar el tar de ~/backups y `docker compose up -d --build`.
set -euo pipefail

HOST="${DEPLOY_HOST:-bruno@nixbox}"
REMOTE_DIR="${DEPLOY_DIR:-/opt/dmac-market-brief-agent}"
REF="${DEPLOY_REF:-main}"
SERVICE="dmac-market-brief-agent"
APPLY=false
[[ "${1:-}" == "--apply" ]] && APPLY=true

cd "$(git rev-parse --show-toplevel)"
if ! git rev-parse --verify --quiet "$REF^{commit}" >/dev/null; then
  echo "Ref no encontrado: $REF" >&2
  exit 1
fi
COMMIT="$(git rev-parse --short "$REF")"

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT
git archive "$REF" | tar -x -C "$WORKDIR"

RSYNC_OPTS=(
  -a --delete
  --exclude='/.env'
  --exclude='/storage/*.db'
  --exclude='/storage/*.db-*'
  --exclude='/credentials/'
  --exclude='/outputs/'
  --exclude='/logs/'
)

echo "Ref: $REF ($COMMIT) -> $HOST:$REMOTE_DIR"
echo "== Cambios (simulacion) =="
rsync "${RSYNC_OPTS[@]}" -n --itemize-changes "$WORKDIR/" "$HOST:$REMOTE_DIR/" | grep -v '^\.d' || true

if ! $APPLY; then
  echo
  echo "Simulacion solamente. Para desplegar: scripts/deploy.sh --apply"
  exit 0
fi

STAMP="$(date +%Y%m%d-%H%M%S)"
echo "== 1. Respaldo =="
ssh "$HOST" "set -e; mkdir -p ~/backups && chmod 700 ~/backups; \
  tar -czf ~/backups/dmac-$STAMP.tgz -C \"\$(dirname $REMOTE_DIR)\" \"\$(basename $REMOTE_DIR)\"; \
  chmod 600 ~/backups/dmac-$STAMP.tgz; ls -la ~/backups/dmac-$STAMP.tgz"

echo "== 2. Sync =="
rsync "${RSYNC_OPTS[@]}" "$WORKDIR/" "$HOST:$REMOTE_DIR/"
ssh "$HOST" "echo '$COMMIT' > $REMOTE_DIR/DEPLOYED_COMMIT"

echo "== 3. Rebuild =="
ssh "$HOST" "cd $REMOTE_DIR && docker compose up -d --build 2>&1 | tail -5"

echo "== 4. Verificacion =="
ssh "$HOST" "cd $REMOTE_DIR; for i in \$(seq 1 12); do \
    status=\$(docker compose ps --format '{{.Status}}'); \
    case \"\$status\" in Up*) break;; esac; sleep 5; done; \
  sleep 15; echo \"Estado: \$(docker compose ps --format '{{.Status}}')\"; \
  if docker compose logs --since 2m $SERVICE 2>&1 | grep -q Traceback; then \
    echo 'ERROR: hay tracebacks en los logs:'; docker compose logs --since 2m $SERVICE 2>&1 | tail -20; exit 1; fi; \
  docker compose exec -T $SERVICE python -m scripts.diagnose_market_data 2>&1 | grep -E 'OK:|SIN DATOS' || true"

echo "Desplegado $REF ($COMMIT). Respaldo: ~/backups/dmac-$STAMP.tgz"
