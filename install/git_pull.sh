#!/bin/bash
if [ -z "${BASH_VERSION:-}" ]; then
    exec /bin/bash "$0" "$@"
fi

set -e

log_file="/home/admin/gunpo/install/git_pull.log"
target_branch="${TARGET_BRANCH:-}"

log_message() {
    echo "$(date): $1" >> "$log_file"
}

ensure_watchdog_installed() {
    local service_name="gunpo-network-watchdog.service"
    local service_file="/etc/systemd/system/${service_name}"
    local installer="/home/admin/gunpo/docker/install_watchdog.sh"

    if [ ! -x "$installer" ]; then
        chmod +x "$installer"
    fi

    if [ ! -f "$service_file" ]; then
        log_message "Watchdog service file missing. Running installer."
        /bin/bash "$installer" >> "$log_file" 2>&1
        return
    fi

    if ! sudo systemctl list-unit-files "$service_name" | grep -q "^${service_name}"; then
        log_message "Watchdog daemon not registered. Running installer."
        /bin/bash "$installer" >> "$log_file" 2>&1
        return
    fi

    if ! sudo systemctl is-enabled "$service_name" >/dev/null 2>&1; then
        log_message "Watchdog service disabled. Enabling."
        sudo systemctl enable "$service_name" >> "$log_file" 2>&1
    fi

    if ! sudo systemctl is-active "$service_name" >/dev/null 2>&1; then
        log_message "Watchdog service inactive. Starting."
        sudo systemctl restart "$service_name" >> "$log_file" 2>&1
    fi
}

if [ "${ONLY_ENSURE_WATCHDOG:-0}" = "1" ]; then
    cd /home/admin/gunpo
    ensure_watchdog_installed
    log_message "Watchdog-only simulation completed."
    exit 0
fi

# 작업 디렉토리 이동
cd /home/admin/gunpo

# sh /home/admin/gunpo/install/git_pull.sh
#git stash
#sudo systemctl restart cv2_ffmpeg
# 최신 코드 가져오기
current_branch="$(git branch --show-current 2>/dev/null || true)"
if [ -z "$target_branch" ]; then
    target_branch="$current_branch"
fi
if [ -z "$target_branch" ]; then
    target_branch="prod"
fi

log_message "Repository update start. current_branch=$current_branch target_branch=$target_branch"

if ! GIT_TERMINAL_PROMPT=0 git fetch origin "$target_branch" >> "$log_file" 2>&1; then
    log_message "git fetch origin $target_branch failed. Skip restart to keep current service healthy."
    exit 0
fi

if ! git checkout "$target_branch" >> "$log_file" 2>&1; then
    if ! git checkout -B "$target_branch" FETCH_HEAD >> "$log_file" 2>&1; then
        log_message "git checkout for $target_branch failed. Skip restart."
        exit 0
    fi
fi

if ! git reset --hard FETCH_HEAD >> "$log_file" 2>&1; then
    log_message "git reset to fetched head failed. Skip restart."
    exit 0
fi
# 변경 사항 복원
#git stash pop

# vnc 서버구성
WAYVNC_SOURCE_FILE="/home/admin/gunpo/install/wayvnc.service"
WAYVNC_TARGET_FILE="/etc/systemd/system/wayvnc.service"
AIR_SOURCE_FILE="/home/admin/gunpo/install/air.service"
AIR_TARGET_FILE="/etc/systemd/system/air.service"
CV2F_SOURCE_FILE="/home/admin/gunpo/install/cv2_ffmpeg.service"
CV2F_TARGET_FILE="/etc/systemd/system/cv2_ffmpeg.service"

sudo cp "$WAYVNC_SOURCE_FILE" "$WAYVNC_TARGET_FILE"
sudo cp "$AIR_SOURCE_FILE" "$AIR_TARGET_FILE"
sudo cp "$CV2F_SOURCE_FILE" "$CV2F_TARGET_FILE"
# systemd 설정 반영 및 서비스 실행
sudo systemctl daemon-reload
sudo systemctl enable wayvnc
sudo systemctl enable cv2_ffmpeg


# 패키지 설치 필요 여부 확인 후 설치 (완료될 때까지 대기)
echo "$(date): Checking and installing required Python packages..." >> /home/admin/gunpo/install/git_pull.log
/home/admin/gunpo/venv/bin/pip install -r /home/admin/gunpo/requirements.txt --no-cache-dir >> /home/admin/gunpo/install/git_pull.log 2>&1

# pip 설치가 정상적으로 완료되었는지 확인
if [ $? -eq 0 ]; then
    echo "$(date): Package installation completed successfully." >> /home/admin/gunpo/install/git_pull.log
else
    echo "$(date): Package installation failed. Check logs for details." >> /home/admin/gunpo/install/git_pull.log
    exit 1  # 오류 발생 시 스크립트 중단
fi

ensure_watchdog_installed


#sh /home/admin/gunpo/docker/run/cv2_yolo.sh stop
sudo systemctl restart cv2_ffmpeg


#ENV_FILE="/home/admin/gunpo/docker/.env"
#sed -i "s/^IP_ADDRESS=.*/IP_ADDRESS_LED=192.168.10.103/" "$ENV_FILE"
#sed -i "s/^IP_ADDRESS_LED=.*/IP_ADDRESS_LED=192.168.10.103/" "$ENV_FILE"
#sed -i "s/^IP_ADDRESS_FAN=.*/IP_ADDRESS_FAN=192.168.10.104/" "$ENV_FILE"

sudo systemctl restart main_ctl
sudo rm -rf /home/admin/gunpo/docker/run/debug_images
sudo find /home/admin/data/debug_images -mindepth 1 -exec rm -rf {} +


# 크론탭에서 'sudo reboot'이 포함된 라인이 있는지 확인
CRON_CMD="0 3 * * * sudo reboot"
CRON_CHECK=$(crontab -l 2>/dev/null | grep -F "$CRON_CMD")

# 크론에 명령어가 없으면 추가
if [ -z "$CRON_CHECK" ]; then
    echo "크론 작업이 없습니다. 추가합니다..."
    (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
    echo "크론탭에 시스템 재부팅 명령이 추가되었습니다: $CRON_CMD"
else
    echo "크론탭에 이미 존재합니다. 변경할 필요 없음."
fi

# 대상 파일 (.bashrc 또는 .bash_aliases)
ALIAS_FILE="$HOME/.bash_aliases"

# alias 확인 및 추가 함수
add_alias_if_missing() {
    local alias_cmd="$1"
    if ! grep -Fxq "$alias_cmd" "$ALIAS_FILE"; then
        echo "$alias_cmd" >> "$ALIAS_FILE"
        echo "추가됨: $alias_cmd"
    else
        echo "이미 존재: $alias_cmd"
    fi
}

add_alias_if_missing "alias applog='tail -f /home/admin/gunpo/docker/logs/app.log'"
add_alias_if_missing "alias apperr='tail -f /home/admin/gunpo/docker/logs/app.err'"
add_alias_if_missing "alias cvlog='tail -f /home/admin/gunpo/docker/logs/cv_yolo.log'"
add_alias_if_missing "alias cvstop='sh /home/admin/gunpo/docker/run/cv2_yolo.sh stop'"
add_alias_if_missing "alias cvstart='sh /home/admin/gunpo/docker/run/cv2_yolo.sh start'"
add_alias_if_missing "alias cvrestart='sh /home/admin/gunpo/docker/run/cv2_yolo.sh restart'"
add_alias_if_missing "alias venv='source /home/admin/gunpo/venv/bin/activate'"
add_alias_if_missing "alias cvfstop='sh /home/admin/gunpo/docker/run/cv2_ffmpeg.sh stop'"
add_alias_if_missing "alias cvfstart='sh /home/admin/gunpo/docker/run/cv2_ffmpeg.sh start'"
add_alias_if_missing "alias cvfrs='sudo systemctl restart cv2_ffmpeg'"
add_alias_if_missing "alias cvflog='tail -f /home/admin/gunpo/docker/logs/cv2_ffmpeg.log'"
add_alias_if_missing "alias apprrs='sudo systemctl restart main_ctl'"

# .bashrc에 .bash_aliases 포함 여부 확인 및 추가
if ! grep -q "bash_aliases" "$HOME/.bashrc"; then
    echo "\nif [ -f ~/.bash_aliases ]; then\n  . ~/.bash_aliases\nfi" >> "$HOME/.bashrc"
    echo "🔧 .bashrc에 ~/.bash_aliases include 추가됨"
fi

echo "Alias 설정 완료!"

count=$(ps aux | grep '[c]hromium' | wc -l)

echo "현재 실행 중인 Chromium 프로세스 수: $count"

if [ "$count" -eq 0 ]; then
    echo "Chromium 없음 → start_browser.py 실행"
     sudo systemctl restart air
elif [ "$count" -gt 13 ]; then
    echo "Chromium 프로세스가 너무 많음 → 종료 후 재시작"
    sudo pkill chromium
    sleep 3
    sudo systemctl restart air
else
    echo "Chromium이 적절하게 실행 중입니다."
fi


# 로그 기록
echo "$(date): main_ctl restarted and repository updated" >> /home/admin/gunpo/install/git_pull.log
