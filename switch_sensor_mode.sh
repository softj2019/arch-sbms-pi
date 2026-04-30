#!/bin/bash

# 센서 모드 전환 스크립트
# 사용법: ./switch_sensor_mode.sh [radar|camera|dual]

MODE=${1:-help}
ENV_FILE="/home/admin/gunpo/docker/.env"

print_usage() {
    cat << EOF
사용법: ./switch_sensor_mode.sh [모드]

모드:
  radar       - 레이더 센서만 활성 (카메라 비활성)
  camera      - 카메라만 활성 (레이더 비활성)
  dual        - 둘 다 활성
  status      - 현재 설정 확인

예시:
  ./switch_sensor_mode.sh radar    # 레이더 전환
  ./switch_sensor_mode.sh camera   # 카메라 전환
  ./switch_sensor_mode.sh status   # 상태 확인
EOF
}

show_status() {
    echo "=== 현재 센서 설정 ==="
    ssh admin@192.168.10.100 "grep -E 'RADAR_ENABLED|CAMERA_ENABLED' $ENV_FILE"
    echo ""
    echo "=== 서비스 상태 ==="
    ssh admin@192.168.10.100 "systemctl status radar_ctl.service cv2_ffmpeg.service main_ctl.service --no-pager | grep -E 'Service|Active|since'"
}

switch_mode() {
    local radar=$1
    local camera=$2
    local mode=$3

    echo "=== 센서 모드 전환: SENSOR_MODE=$mode, RADAR=$radar, CAMERA=$camera ==="

    ssh admin@192.168.10.100 << EOSSH
        echo "1. .env 수정 중..."
        sed -i "s/SENSOR_MODE=.*/SENSOR_MODE=$mode/g" $ENV_FILE
        sed -i "s/RADAR_ENABLED=.*/RADAR_ENABLED=$radar/g" $ENV_FILE
        sed -i "s/CAMERA_ENABLED=.*/CAMERA_ENABLED=$camera/g" $ENV_FILE

        echo "2. 설정 확인..."
        grep -E 'RADAR_ENABLED|CAMERA_ENABLED' $ENV_FILE

        echo ""
        echo "3. 서비스 재시작 중..."
        sudo systemctl restart radar_ctl.service cv2_ffmpeg.service main_ctl.service
        sleep 3

        echo ""
        echo "4. 서비스 상태..."
        systemctl status radar_ctl.service cv2_ffmpeg.service main_ctl.service --no-pager | grep -E 'Service|Active|since'
EOSSH
}

case $MODE in
    radar)
        switch_mode "true" "false" "radar"
        ;;
    camera)
        switch_mode "false" "true" "camera"
        ;;
    dual)
        switch_mode "true" "true" "both"
        ;;
    status)
        show_status
        ;;
    help|--help|-h)
        print_usage
        ;;
    *)
        echo "❌ 알 수 없는 모드: $MODE"
        echo ""
        print_usage
        exit 1
        ;;
esac

echo ""
echo "✓ 완료"
