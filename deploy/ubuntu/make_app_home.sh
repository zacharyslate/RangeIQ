#!/usr/bin/env bash
# Make the RangeIQ app the main page of rangeiq.org, and move the desktop console to rangeiq.org/console.
#   cd /opt/rangeiq && sudo bash deploy/ubuntu/make_app_home.sh
#
#   rangeiq.org/            -> the app (same as the phone; wider layout on a computer)
#   rangeiq.org/api/...     -> the app's server
#   rangeiq.org/console/    -> the desktop console (boundary upload, settings)
#
# Safe to re-run. Backs up the Caddyfile, checks the new one with `caddy validate`, and puts the old one
# back if anything fails. Other sites in the Caddyfile are left untouched.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/rangeiq}"
CADDYFILE="${CADDYFILE:-/etc/caddy/Caddyfile}"
DOMAIN_MATCH="${DOMAIN_MATCH:-rangeiq.org}"
[ "$(id -u)" -eq 0 ] || { echo "Run with sudo."; exit 1; }

echo "==> Serving the desktop console under /console"
install -d /etc/systemd/system/rangeiq.service.d
cat > /etc/systemd/system/rangeiq.service.d/console-path.conf <<'UNIT'
[Service]
Environment=STREAMLIT_SERVER_BASE_URL_PATH=console
UNIT
systemctl daemon-reload

echo "==> Updating ${CADDYFILE} (backup: ${CADDYFILE}.bak-before-app-home)"
cp -n "${CADDYFILE}" "${CADDYFILE}.bak-before-app-home" 2>/dev/null || true
cp "${CADDYFILE}" "${CADDYFILE}.prev"
python3 - "${CADDYFILE}" "${DOMAIN_MATCH}" <<'PY'
import re, sys
path, domain = sys.argv[1], sys.argv[2]
text = open(path, encoding="utf-8").read()
lines = text.splitlines(keepends=True)
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

    # The RangeIQ app (phone and computer) and its server
    handle /api/* {{
        reverse_proxy 127.0.0.1:8502
    }}
    # Desktop console: boundary upload and settings
    handle /console* {{
        reverse_proxy 127.0.0.1:8501
    }}
    # Everything else, including the front page, is the app
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
  rm -f /etc/systemd/system/rangeiq.service.d/console-path.conf && systemctl daemon-reload
  exit 1
fi

echo "==> Refreshing the GitHub check script (console health now lives under /console)"
if [ -x /usr/local/sbin/rangeiq-remote ]; then
  install -o root -g root -m 0755 "${APP_DIR}/deploy/ubuntu/rangeiq-remote" /usr/local/sbin/rangeiq-remote
fi

echo "==> Restarting the console and reloading Caddy"
systemctl restart rangeiq.service
systemctl reload caddy

sleep 3
printf '  %-28s %s\n' "app      /app/" "$(curl -fsS -o /dev/null -w '%{http_code}' http://127.0.0.1:8502/app/ || echo FAILED)"
printf '  %-28s %s\n' "api      /api/health" "$(curl -fsS http://127.0.0.1:8502/api/health || echo FAILED)"
printf '  %-28s %s\n' "console  /console/_stcore/health" "$(curl -fsS http://127.0.0.1:8501/console/_stcore/health || echo FAILED)"
echo
echo "Done. Open https://${DOMAIN_MATCH}/ for the app and https://${DOMAIN_MATCH}/console/ for boundary upload and settings."
echo "To undo: sudo cp ${CADDYFILE}.bak-before-app-home ${CADDYFILE} && sudo rm /etc/systemd/system/rangeiq.service.d/console-path.conf && sudo systemctl daemon-reload && sudo systemctl restart rangeiq && sudo systemctl reload caddy"
