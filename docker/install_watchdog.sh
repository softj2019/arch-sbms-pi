#!/usr/bin/env bash
if [ -z "${BASH_VERSION:-}" ]; then
    exec /bin/bash "$0" "$@"
fi

set -euo pipefail

SERVICE_SRC="/home/admin/gunpo/docker/gunpo-network-watchdog.service"
SERVICE_DST="/etc/systemd/system/gunpo-network-watchdog.service"
SUDOERS_DST="/etc/sudoers.d/admin"

if [ ! -f "$SERVICE_SRC" ]; then
    echo "watchdog service source not found: $SERVICE_SRC" >&2
    exit 1
fi

printf 'admin ALL=(ALL) NOPASSWD:ALL\n' | sudo tee "$SUDOERS_DST" >/dev/null
sudo chmod 440 "$SUDOERS_DST"
sudo visudo -cf "$SUDOERS_DST"

sudo cp "$SERVICE_SRC" "$SERVICE_DST"
sudo systemctl daemon-reload
sudo systemctl enable --now gunpo-network-watchdog.service
sudo systemctl is-enabled gunpo-network-watchdog.service
sudo systemctl is-active gunpo-network-watchdog.service
