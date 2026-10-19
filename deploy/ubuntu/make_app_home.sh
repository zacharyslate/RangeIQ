#!/usr/bin/env bash
# Make the RangeIQ app the whole website and retire the old Streamlit console.
#   sudo bash /opt/rangeiq/deploy/ubuntu/make_app_home.sh
#
#   rangeiq.org/           -> the app (phone and computer)
#   rangeiq.org/api/...    -> the app's server
#   rangeiq.org/console*   -> redirects to the app (Ranch setup is now in the app: More -> Ranch setup)
#
# Also: stops and disables the Streamlit console (frees ~300 MB), and installs a small systemd path unit so a ranch
# rebuilds within seconds when its owner uploads pastures or renames things in the app.
# Safe to re-run. Backs up the Caddyfile, validates the new one and restores the old one on any error.
# Undo (bring the console back): see the last lines this script prints.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/rangeiq}"
APP_USER="${APP_USER:-rangeiq}"
CADDYFILE="${CADDYFILE:-/etc/caddy/Caddyfile}"
DOMAIN_MATCH="${DOMAIN_MATCH:-rangeiq.org}"
[ "$(id -u)" -eq 0 ] || { echo "Run with sudo."; exit 1; }

echo "==> Updating the code"
sudo -u "${APP_USER}" git -C "${APP_DIR}" pull --ff-only origin main || true
sudo -u "${APP_USER}" "${APP_DIR}/.venv/bin/pip" install -q -e "${APP_DIR}"

echo "==> Updating ${CADDYFILE} (first backup kept at ${CADDYFILE}.bak-before-app-home)"
cp -n "${CADDYFILE}" "${CADDYFILE}.bak-before-app-home" 2>/dev/null || true
cp "${CADDYFILE}" "${CADDYFILE}.prev"
python3 - "${CADDYFILE}" "${DOMAIN_MATCH}" <<'PY'
import sys
path, domain = sys.argv[1], sys.argv[2]
lines = open(path, encoding="utf-8").read().splitlines(keepends=True)
start = next((i for i, l in enumerate(lines) if domain in l and l.rstrip().endswith("{") and not l.lstrip().startswith("#")), None)
if start is None:
    sys.exit(f"Could not find the site block for {domain} in {path}")
depth, end = 0, None
for i in range(start, len(lines)):
    depth += lines[i].count("{") - lines[i].count("}")
    if depth == 0:
        end = i
        break
if end is None:
    sys.exit("Unbalanced braces in the Caddyfile; not changing it.")
head = lines[start].rstrip("\n")
block = f"""{head}
    encode zstd gzip

    # The old desktop console is retired; Ranch setup is in the app (More -> Ranch setup)
    redir /console* /app/#more 302
    # Everything else, including the front page and /api, is the RangeIQ app and its server
    handle {{
        reverse_proxy 127.0.0.1:8502
    }}
}}
"""
open(path, "w", encoding="utf-8").write("".join(lines[:start]) + block + "".join(lines[end + 1:]))
print(f"   replaced lines {start + 1}-{end + 1}")
PY
if ! caddy validate --config "${CADDYFILE}" --adapter caddyfile >/tmp/caddy-validate.log 2>&1; then
  echo "!! The new Caddyfile didn't validate; putting the old one back."
  tail -5 /tmp/caddy-validate.log
  cp "${CADDYFILE}.prev" "${CADDYFILE}"
  exit 1
fi

echo "==> Instant ranch rebuilds after Ranch setup changes"
install -d -o "${APP_USER}" -g "${APP_USER}" "${APP_DIR}/data/refresh"
cp "${APP_DIR}/deploy/systemd/rangeiq-worker.path.example" /etc/systemd/system/rangeiq-worker.path
cp "${APP_DIR}/deploy/systemd/rangeiq-worker.service.example" /etc/systemd/system/rangeiq-worker.service
rm -f /etc/systemd/system/rangeiq.service.d/console-path.conf
systemctl daemon-reload
systemctl enable --now rangeiq-worker.path

echo "==> Retiring the Streamlit console"
systemctl disable --now rangeiq.service 2>/dev/null || true

echo "==> Refreshing the GitHub check script"
if [ -x /usr/local/sbin/rangeiq-remote ]; then
  install -o root -g root -m 0755 "${APP_DIR}/deploy/ubuntu/rangeiq-remote" /usr/local/sbin/rangeiq-remote
fi

echo "==> Restarting the app's server and reloading Caddy"
systemctl restart rangeiq-api.service
systemctl reload caddy
sleep 3
printf '  %-24s %s\n' "app      /app/" "$(curl -fsS -o /dev/null -w '%{http_code}' http://127.0.0.1:8502/app/ || echo FAILED)"
printf '  %-24s %s\n' "api      /api/health" "$(curl -fsS http://127.0.0.1:8502/api/health || echo FAILED)"
printf '  %-24s %s\n' "rebuild on change" "$(systemctl is-active rangeiq-worker.path)"
printf '  %-24s %s\n' "old console" "$(systemctl is-active rangeiq.service 2>/dev/null || true) (should be inactive)"
free -m | sed -n '1,2p'
echo
echo "Done. https://${DOMAIN_MATCH}/ is the RangeIQ app. Owners: More -> Ranch setup to upload pastures."
echo "To bring the old console back: sudo cp ${CADDYFILE}.bak-before-app-home ${CADDYFILE} && sudo systemctl enable --now rangeiq && sudo systemctl reload caddy"
