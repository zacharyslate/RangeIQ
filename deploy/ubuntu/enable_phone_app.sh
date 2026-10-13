#!/usr/bin/env bash
# One-time setup of the RangeIQ phone app on a server that already runs RangeIQ.
#   cd /opt/rangeiq && sudo bash deploy/ubuntu/enable_phone_app.sh
# Safe to re-run.
set -euo pipefail

APP_USER="${APP_USER:-rangeiq}"
APP_DIR="${APP_DIR:-/opt/rangeiq}"
CADDYFILE="${CADDYFILE:-/etc/caddy/Caddyfile}"

echo "==> Installing Python dependencies (adds FastAPI + Uvicorn)"
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install -q -e "${APP_DIR}"

echo "==> Installing systemd units"
sudo cp "${APP_DIR}/deploy/systemd/rangeiq-api.service.example" /etc/systemd/system/rangeiq-api.service
sudo cp "${APP_DIR}/deploy/systemd/rangeiq-worker.service.example" /etc/systemd/system/rangeiq-worker.service
sudo cp "${APP_DIR}/deploy/systemd/rangeiq-worker.timer.example" /etc/systemd/system/rangeiq-worker.timer
sudo systemctl daemon-reload
sudo systemctl enable --now rangeiq-api.service
sudo systemctl enable --now rangeiq-worker.timer

echo "==> First worker run (builds each ranch's snapshot; can take a few minutes)"
sudo systemctl start rangeiq-worker.service || true
sudo journalctl -u rangeiq-worker.service -n 20 --no-pager || true

echo "==> Checking the API"
curl -fsS http://127.0.0.1:8502/api/health && echo

if [ -f "${CADDYFILE}" ] && ! grep -q "8502" "${CADDYFILE}"; then
  cat <<EOF

ACTION NEEDED: add the phone-app routes to ${CADDYFILE}.
Inside your site block, before the existing reverse_proxy line, add:

    handle /app* {
        reverse_proxy 127.0.0.1:8502
    }
    handle /api/* {
        reverse_proxy 127.0.0.1:8502
    }

and wrap the existing 'reverse_proxy 127.0.0.1:8501' in 'handle { ... }'.
See deploy/caddy/Caddyfile.example. Then run:  sudo systemctl reload caddy
EOF
else
  sudo systemctl reload caddy 2>/dev/null || true
  echo "==> Caddy already routes the phone app."
fi

echo
echo "Done. On your phone, open https://YOUR-DOMAIN/app/ and sign in."
