#!/bin/sh

# 서비스 파일 경로 설정
SERVICE_FILE="air.service"
DEST_PATH="/etc/systemd/system/$SERVICE_FILE"
WLR_SERVICE_FILE="wlr.service"
WLR_DEST_PATH="/etc/systemd/system/$WLR_SERVICE_FILE"
# Chromium Preferences 파일 경로
PREF_SOURCE="/home/admin/gunpo/install/Preferences"
PREF_DEST="/home/admin/.config/chromium/Default/Preferences"
# 서비스 파일이 존재하는지 확인
if [ ! -f "$SERVICE_FILE" ]; then
    echo "❌ 오류: $SERVICE_FILE 파일이 현재 디렉토리에 존재하지 않습니다!"
    exit 1
fi
if [ ! -f "$WLR_SERVICE_FILE" ]; then
    echo "❌ 오류: WLR_SERVICE_FILE 파일이 현재 디렉토리에 존재하지 않습니다!"
    exit 1
fi
# 서비스 파일을 시스템 서비스 디렉토리로 복사
echo "📂 $SERVICE_FILE 파일을 $DEST_PATH 로 복사 중..."
sudo cp "$SERVICE_FILE" "$DEST_PATH"

echo "📂 $WLR_SERVICE_FILE 파일을 $WLR_DEST_PATH 로 복사 중..."
sudo cp "$WLR_SERVICE_FILE" "$WLR_DEST_PATH"

# 서비스 활성화 및 실행
echo "🔄 systemctl daemon-reload 실행..."
sudo systemctl daemon-reload

echo "✅ systemctl enable $SERVICE_FILE 실행..."
sudo systemctl enable "$SERVICE_FILE"
echo "✅ systemctl enable $WLR_SERVICE_FILE 실행..."
sudo systemctl enable "$WLR_SERVICE_FILE"

# 서비스 상태 확인
echo "📌 서비스 상태 확인:"
sudo systemctl status "$SERVICE_FILE" --no-pager
sudo systemctl status "$WLR_SERVICE_FILE" --no-pager
echo "✅ 서비스 설치 및 실행 완료!"

# 환경 변수 파일 경로
ENV_FILE="/home/admin/gunpo/docker/.env"

# `.env` 파일이 존재하는지 확인
if [ ! -f "$ENV_FILE" ]; then
    echo "❌ 오류: 환경 변수 파일($ENV_FILE)이 존재하지 않습니다!"
    exit 1
fi
# 사용자로부터 호스트네임 입력받기
echo -n "hostname 입력(엔터:유지): "
read new_hostname

# 입력값이 비어있지 않은 경우에만 변경 수행
if [ -n "$new_hostname" ]; then
    # 호스트네임 변경
    sudo hostnamectl set-hostname "$new_hostname"
    echo "변경된 Hostname $new_hostname"

    # /etc/hosts 파일 수정
    sudo sed -i "s/127.0.1.1.*/127.0.1.1 $new_hostname/" /etc/hosts
    echo "/etc/hosts 업데이트 hostname."

else
    echo "문제가 발생했습니다. 다시 실행해주세요"
fi


# 현재 설정 값 출력
echo "📌 현재 설정된 값:"
CURRENT_TERMINAL_ID=$(grep -E "^TERMINAL_ID=" "$ENV_FILE" | cut -d '=' -f2)
CURRENT_IP_ADDRESS_LED=$(grep -E "^IP_ADDRESS_LED=" "$ENV_FILE" | cut -d '=' -f2)
CURRENT_IP_ADDRESS_FAN=$(grep -E "^IP_ADDRESS_FAN=" "$ENV_FILE" | cut -d '=' -f2)

echo "🔹 TERMINAL_ID: ${CURRENT_TERMINAL_ID:-없음}"
echo "🔹 IP_ADDRESS_LED: ${CURRENT_IP_ADDRESS_LED:-없음}"
echo "🔹 IP_ADDRESS_FAN: ${CURRENT_IP_ADDRESS_FAN:-없음}"

# 새로운 값 입력 (입력 없으면 기존 값 유지)
read -p "📝 새로운 TERMINAL_ID (Enter 키를 누르면 기존 값 유지): " NEW_TERMINAL_ID
read -p "📝 새로운 IP_ADDRESS_LED (Enter 키를 누르면 기존 값 유지): " NEW_IP_ADDRESS_LED
read -p "📝 새로운 IP_ADDRESS_FAN (Enter 키를 누르면 기존 값 유지): " NEW_IP_ADDRESS_FAN

# 기존 값 유지 또는 새로운 값으로 업데이트
if [ ! -z "$NEW_TERMINAL_ID" ]; then
    sed -i "s/^TERMINAL_ID=.*/TERMINAL_ID=$NEW_TERMINAL_ID/" "$ENV_FILE"
fi
if [ ! -z "$NEW_IP_ADDRESS_LED" ]; then
    sed -i "s/^IP_ADDRESS_LED=.*/IP_ADDRESS_LED=$NEW_IP_ADDRESS_LED/" "$ENV_FILE"
fi
if [ ! -z "$NEW_IP_ADDRESS_FAN" ]; then
    sed -i "s/^IP_ADDRESS_FAN=.*/IP_ADDRESS_FAN=$NEW_IP_ADDRESS_FAN/" "$ENV_FILE"
fi

# 변경된 값 출력
echo "✅ .env 파일이 성공적으로 업데이트 되었습니다!"
echo "📌 변경된 값:"
grep -E "TERMINAL_ID|IP_ADDRESS_LED|IP_ADDRESS_FAN" "$ENV_FILE"

# -------------------
# 3️⃣ Chromium Preferences 파일 복사
# -------------------
echo "📂 Chromium Preferences 설정을 복사 중..."

# `.config/chromium/Default/Preferences` 디렉토리가 존재하는지 확인 후 복사
if [ -f "$PREF_SOURCE" ]; then
    sudo mkdir -p "$(dirname "$PREF_DEST")"
    sudo cp "$PREF_SOURCE" "$PREF_DEST"
    sudo chown admin:admin "$PREF_DEST"  # 사용자 계정에 맞게 변경 필요
    echo "✅ Chromium Preferences 설정이 복사되었습니다!"
else
    echo "⚠️ Chromium Preferences 파일을 찾을 수 없습니다: $PREF_SOURCE"
fi

echo "rustdesk 설정을 복사 중..."

# 자동 실행 디렉토리 경로 설정
autostart_dir="$HOME/.config/autostart"
desktop_file="/home/admin/gunpo/install/rustdesk.desktop"

# 자동 실행 디렉토리가 없으면 생성
if [ ! -d "$autostart_dir" ]; then
    echo "Creating autostart directory: $autostart_dir"
    mkdir -p "$autostart_dir"
fi

# rustdesk.desktop 파일이 현재 디렉토리에 있는지 확인
if [ -f "$desktop_file" ]; then
    echo "Copying $desktop_file to $autostart_dir"
    cp "$desktop_file" "$autostart_dir/"
    chmod +x "$autostart_dir/$desktop_file"
    echo "Done! RustDesk will now start automatically on login."
else
    echo "Error: $desktop_file not found in the current directory."
    exit 1
fi

echo "🚀 systemctl start $SERVICE_FILE 실행..."
sudo systemctl start "$SERVICE_FILE"
echo "🚀 systemctl start $WLR_SERVICE_FILE 실행..."
sudo systemctl start "$WLR_SERVICE_FILE"