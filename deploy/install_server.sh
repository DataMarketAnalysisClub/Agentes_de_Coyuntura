#!/usr/bin/env bash
# Install dmac-market-brief-agent as a systemd-managed Docker Compose service.
#
# Usage:
#   sudo ./deploy/install_server.sh
#
# Requirements:
#   - Debian/Ubuntu with Docker Engine + docker compose plugin
#   - The repo deployed at /opt/dmac-market-brief-agent
#   - .env configured with real credentials (not the placeholder)
#   - credentials/bcentral.txt present on the host (optional)
#
# Full deploy guide: see DEPLOY.md

set -euo pipefail

SERVICE_USER="${SERVICE_USER:-root}"
INSTALL_DIR="${INSTALL_DIR:-/opt/dmac-market-brief-agent}"
SERVICE_FILE_SRC="$(dirname "$0")/systemd/dmac-market-brief-agent.service"
SERVICE_FILE_DST="/etc/systemd/system/dmac-market-brief-agent.service"

if [ ! -d "$INSTALL_DIR" ]; then
    echo "ERROR: install dir $INSTALL_DIR not found." >&2
    echo "       Create it first: sudo mkdir -p $INSTALL_DIR && sudo chown \$USER:\$USER $INSTALL_DIR" >&2
    echo "       Then rsync/upload the project files into it." >&2
    exit 1
fi

if [ ! -f "$INSTALL_DIR/.env" ]; then
    echo "ERROR: $INSTALL_DIR/.env not found." >&2
    echo "" >&2
    echo "Setup instructions:" >&2
    echo "  cd $INSTALL_DIR" >&2
    echo "  cp .env.production.example .env" >&2
    echo "  chmod 600 .env" >&2
    echo "  nano .env   # fill OLLAMA_API_KEY, SMTP_PASSWORD, EMAIL_TO, etc." >&2
    exit 1
fi

# Basic sanity: ensure placeholder values were replaced
if grep -q "<GMAIL_APP_PASSWORD>" "$INSTALL_DIR/.env" 2>/dev/null \
   || grep -q "<OLLAMA_API_KEY>" "$INSTALL_DIR/.env" 2>/dev/null \
   || grep -q "<BCCH_USER>" "$INSTALL_DIR/.env" 2>/dev/null; then
    echo "ERROR: $INSTALL_DIR/.env still contains placeholder values." >&2
    echo "       Edit with 'nano $INSTALL_DIR/.env' and replace all <PLACEHOLDER> entries." >&2
    exit 1
fi

if [ ! -d "$INSTALL_DIR/credentials" ]; then
    echo "WARN: $INSTALL_DIR/credentials not found. Creating empty dir (BCCh auth will be skipped)."
    mkdir -p "$INSTALL_DIR/credentials"
    chmod 700 "$INSTALL_DIR/credentials"
fi

chmod 600 "$INSTALL_DIR/.env"
chmod 700 "$INSTALL_DIR/credentials"

install -m 0644 "$SERVICE_FILE_SRC" "$SERVICE_FILE_DST"
sed -i "s|/opt/dmac-market-brief-agent|$INSTALL_DIR|g" "$SERVICE_FILE_DST"

systemctl daemon-reload
systemctl enable dmac-market-brief-agent.service
systemctl restart dmac-market-brief-agent.service

echo ""
echo "Service installed and started."
echo ""
echo "Verify with:"
echo "  systemctl status dmac-market-brief-agent"
echo "  journalctl -u dmac-market-brief-agent -f"
echo "  cd $INSTALL_DIR && docker compose ps"
echo ""
echo "Schedule (America/Santiago):"
echo "  - morning_brief:    mon-fri 08:30"
echo "  - market_close:     mon-fri 18:30"
echo "  - high_impact_mon:  every 15 min"
echo ""
echo "Manual run: cd $INSTALL_DIR && docker compose exec dmac-market-brief-agent python -m app.main morning"
