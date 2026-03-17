#!/bin/sh

# RustDesk 종료
echo "RustDesk 프로세스 종료 중..."
sudo pkill rustdesk 2>/dev/null

# RustDesk 설정 파일 경로
CONFIG_FILE="$HOME/.config/rustdesk/RustDesk.toml"

# 설정 파일이 존재하는지 확인
if [ -f "$CONFIG_FILE" ]; then
    echo "enc_id 초기화 중..."

    # enc_id 값을 정확히 ''로 변경
    sed -i "s/^enc_id *= *'.*'/enc_id = ''/" "$CONFIG_FILE"

    # 변경된 내용 확인
    echo "변경된 내용:"
    grep "enc_id" "$CONFIG_FILE"
else
    echo "설정 파일을 찾을 수 없습니다: $CONFIG_FILE"
    exit 1
fi

# RustDesk 재시작
echo "RustDesk 재시작 중..."
nohup rustdesk >/dev/null 2>&1 &

echo "✅ RustDesk ID 초기화 완료! (enc_id = '')"
