#!/usr/bin/env bash
set -euo pipefail

APP_USER="${APP_USER:-rangeiq}"
APP_DIR="${APP_DIR:-/opt/rangeiq}"
BRANCH="${BRANCH:-main}"
SERVICE_NAME="${SERVICE_NAME:-rangeiq}"

run_as_app_user() {
  if [ "$(id -un)" = "${APP_USER}" ]; then
    "$@"
  else
    sudo -u "${APP_USER}" "$@"
  fi
}

run_as_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

if [ -n "${DEPLOY_COMMIT:-}" ]; then
  echo "==> Deploy target commit: ${DEPLOY_COMMIT}"
fi

echo "==> Updating RangeIQ in ${APP_DIR}"
run_as_app_user git -C "${APP_DIR}" fetch origin
run_as_app_user git -C "${APP_DIR}" checkout "${BRANCH}"
run_as_app_user git -C "${APP_DIR}" pull --ff-only origin "${BRANCH}"

echo "==> Refreshing Python dependencies"
run_as_app_user "${APP_DIR}/.venv/bin/pip" install -e "${APP_DIR}"

echo "==> Restarting ${SERVICE_NAME}"
run_as_root systemctl restart "${SERVICE_NAME}"
run_as_root systemctl is-active --quiet "${SERVICE_NAME}"

echo "==> ${SERVICE_NAME} is active"
run_as_root journalctl -u "${SERVICE_NAME}" -n 20 --no-pager
