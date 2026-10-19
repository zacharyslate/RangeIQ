#!/usr/bin/env bash
# One-time: let GitHub Actions deploy and check RangeIQ on this server, safely.
#   cd /opt/rangeiq && sudo bash deploy/ubuntu/setup_github_access.sh
#
# Creates a locked-down user 'rangeiq-ci' whose SSH key can ONLY run
# /usr/local/sbin/rangeiq-remote (deploy | check | refresh | diagnose | logs).
# No shell, no port forwarding. Re-running is safe and also refreshes the command script.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/rangeiq}"
CI_USER="rangeiq-ci"
REMOTE=/usr/local/sbin/rangeiq-remote
KEY_DIR=/root/rangeiq-ci-key

[ "$(id -u)" -eq 0 ] || { echo "Run with sudo."; exit 1; }

echo "==> Installing the allowed-commands script (root-owned, outside the app folder)"
install -o root -g root -m 0755 "${APP_DIR}/deploy/ubuntu/rangeiq-remote" "${REMOTE}"

if ! id "${CI_USER}" >/dev/null 2>&1; then
  echo "==> Creating ${CI_USER}"
  useradd --system --create-home --shell /bin/bash "${CI_USER}"
  passwd -l "${CI_USER}" >/dev/null
fi

echo "==> Allowing ${CI_USER} to run only ${REMOTE} as root"
printf '%s ALL=(root) NOPASSWD: %s\nDefaults:%s env_keep += "SSH_ORIGINAL_COMMAND"\n' "${CI_USER}" "${REMOTE}" "${CI_USER}" > /etc/sudoers.d/rangeiq-ci
chmod 0440 /etc/sudoers.d/rangeiq-ci
visudo -cf /etc/sudoers.d/rangeiq-ci >/dev/null

if [ ! -f "${KEY_DIR}/id_ed25519" ]; then
  echo "==> Creating the deploy key"
  install -d -m 700 "${KEY_DIR}"
  ssh-keygen -q -t ed25519 -N "" -C "github-actions-rangeiq" -f "${KEY_DIR}/id_ed25519"
fi

echo "==> Locking the key to the allowed commands"
install -d -m 700 -o "${CI_USER}" -g "${CI_USER}" "/home/${CI_USER}/.ssh"
OPTS="command=\"sudo ${REMOTE}\",no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty"
printf '%s %s\n' "${OPTS}" "$(cat "${KEY_DIR}/id_ed25519.pub")" > "/home/${CI_USER}/.ssh/authorized_keys"
chown "${CI_USER}:${CI_USER}" "/home/${CI_USER}/.ssh/authorized_keys"
chmod 600 "/home/${CI_USER}/.ssh/authorized_keys"

HOST_IP="$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || hostname -I | awk '{print $1}')"
cat <<EOF

=====================================================================
Add these three secrets in GitHub:
  github.com/zacharyslate/RangeIQ -> Settings -> Secrets and variables -> Actions -> New repository secret

  DROPLET_HOST             ${HOST_IP}
  DROPLET_USER             ${CI_USER}
  DROPLET_SSH_PRIVATE_KEY  (everything between the lines below, including BEGIN/END)
---------------------------------------------------------------------
$(cat "${KEY_DIR}/id_ed25519")
---------------------------------------------------------------------
After pasting it into GitHub you can delete the local copy:
  sudo rm -rf ${KEY_DIR}
To revoke access at any time:
  sudo rm /home/${CI_USER}/.ssh/authorized_keys
=====================================================================
EOF
