#!/usr/bin/env bash
###############################################################################
# deploy/install_services.sh
#
# deploy/systemd/ 의 .service 파일을 /etc/systemd/system/ 에 설치하고
# 활성화합니다. Pi 장치에서 직접 실행하거나 deploy_from_local.sh 에서 호출됩니다.
#
# 사용법:
#   bash deploy/install_services.sh
###############################################################################
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYSTEMD_SRC="$SCRIPT_DIR/systemd"
SYSTEMD_DST="/etc/systemd/system"

SERVICES=(main_ctl gunpo-network-watchdog boot-report)

echo "[install_services] 서비스 파일 설치 시작..."

for svc in "${SERVICES[@]}"; do
    src="$SYSTEMD_SRC/${svc}.service"
    dst="$SYSTEMD_DST/${svc}.service"

    if [ ! -f "$src" ]; then
        echo "  SKIP: $src 없음"
        continue
    fi

    sudo cp "$src" "$dst"
    sudo systemctl enable "$svc" 2>/dev/null || true
    echo "  OK: $svc → $dst"
done

sudo systemctl daemon-reload
echo "[install_services] daemon-reload 완료"

for svc in "${SERVICES[@]}"; do
    state=$(systemctl is-active "$svc" 2>/dev/null || echo "inactive")
    echo "  $svc: $state"
done

echo "[install_services] 완료"
