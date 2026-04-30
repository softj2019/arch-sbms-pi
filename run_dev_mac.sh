#!/bin/bash
# Mac 개발 환경 실행 스크립트
# 사용: ./run_dev_mac.sh [이미지/영상 경로]
# 예시: ./run_dev_mac.sh ~/sample.jpg
#       ./run_dev_mac.sh ~/sample.mp4

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$HOME/.cache/sbms-cv-env"

# 가상환경 생성 및 패키지 설치
if [ ! -f "$VENV/bin/python3" ]; then
  echo "==> 가상환경 생성 중..."
  python3 -m venv "$VENV"
  "$VENV/bin/pip" install --upgrade pip -q
  echo "==> 패키지 설치 중 (처음 실행 시 수 분 소요)..."
  "$VENV/bin/pip" install -q \
    "numpy<2" \
    "opencv-python-headless" \
    "ultralytics" \
    "torch" \
    "requests" \
    "python-dotenv" \
    "websockets" \
    "flask"
  echo "==> 설치 완료"
fi

SRC="${1:-}"
if [ -z "$SRC" ]; then
  # 기본 테스트 이미지 생성
  SRC="$HOME/.cache/sbms-cv/test_frame.jpg"
  mkdir -p "$HOME/.cache/sbms-cv"
  if [ ! -f "$SRC" ]; then
    "$VENV/bin/python3" -c "
import numpy as np, cv2, os
img = np.zeros((480,640,3), dtype=np.uint8)
img[100:400, 200:440] = (50, 150, 50)   # 녹색 사각형 (사람 대체)
cv2.putText(img, 'TEST FRAME', (180,260), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (200,200,200), 2)
cv2.imwrite('$SRC', img)
print('테스트 이미지 생성:', '$SRC')
"
  fi
  CV_TYPE="image"
elif echo "$SRC" | grep -qiE '\.mp4$|\.avi$|\.mov$|\.mkv$'; then
  CV_TYPE="video"
else
  CV_TYPE="image"
fi

echo ""
echo "==> 디버그 스트림 시작"
echo "    소스: $SRC ($CV_TYPE)"
echo "    브라우저: http://localhost:8089"
echo "    스카이뷰: http://localhost:8089  (메인 페이지에 통합)"
echo "    종료: Ctrl+C"
echo ""

export ENV_TYPE=dev
export SKIP_SENDS=true
export SENSOR_MODE=camera
export RADAR_SOURCE=disabled
export CV_SOURCE="$CV_TYPE"
export CV_SOURCE_PATH="$SRC"
export API_URL=http://localhost:5000
export DEBUG_STREAM_PORT=8089
export PYTHONPATH="$SCRIPT_DIR/docker/core:$PYTHONPATH"

exec "$VENV/bin/python3" "$SCRIPT_DIR/docker/cv/cv_ffmpeg.py"
