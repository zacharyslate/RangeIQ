#!/usr/bin/env bash
set -euo pipefail

APP_USER="${APP_USER:-rangeiq}"
APP_DIR="${APP_DIR:-/opt/rangeiq}"
REPO_URL="${REPO_URL:-https://github.com/zacharyslate/RangeIQ.git}"
BRANCH="${BRANCH:-main}"

echo "==> Installing base packages"
sudo apt-get update
sudo apt-get install -y git python3 python3-venv python3-pip build-essential

if ! id "${APP_USER}" >/dev/null 2>&1; then
  echo "==> Creating app user: ${APP_USER}"
  sudo useradd --system --create-home --shell /bin/bash "${APP_USER}"
fi

echo "==> Preparing application directory"
sudo mkdir -p "${APP_DIR}"

if [ ! -d "${APP_DIR}/.git" ]; then
  echo "==> Cloning RangeIQ into ${APP_DIR}"
  sudo git clone --branch "${BRANCH}" "${REPO_URL}" "${APP_DIR}"
else
  echo "==> Updating existing checkout"
  sudo git -C "${APP_DIR}" fetch origin
  sudo git -C "${APP_DIR}" checkout "${BRANCH}"
  sudo git -C "${APP_DIR}" pull --ff-only origin "${BRANCH}"
fi

sudo chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"

echo "==> Creating virtual environment"
sudo -u "${APP_USER}" python3 -m venv "${APP_DIR}/.venv"
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install --upgrade pip

echo "==> Installing RangeIQ"
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install -e "${APP_DIR}"

cat <<EOF

Bootstrap complete.

Next steps:
1. Review ${APP_DIR}/config.example.yaml and create ${APP_DIR}/config.yaml if needed.
2. Copy deploy/systemd/rangeiq.service.example to /etc/systemd/system/rangeiq.service
3. Copy deploy/caddy/Caddyfile.example into your Caddy config and replace the hostname
4. Start the service:
   sudo systemctl daemon-reload
   sudo systemctl enable --now rangeiq
5. Check logs:
   sudo journalctl -u rangeiq -f
6. For repeat deploys later:
   bash ${APP_DIR}/deploy/ubuntu/update_rangeiq.sh

EOF
