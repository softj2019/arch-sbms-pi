#!/bin/bash

# HDMI 출력명
OUTPUT="HDMI-A-1"

# 현재 활성화된 해상도 확인
CURRENT_MODE=$(wlr-randr | grep "$OUTPUT" | grep '*' | awk '{print $2}')

# 모드 전환
if [[ "$CURRENT_MODE" == "1280x1024" ]]; then
    # 720x480 해상도로 변경 + 270도 회전
    wlr-randr --output $OUTPUT --mode 720x480 --transform 270
    echo "Switched to 720x480 with 270-degree rotation."
else
    # 1280x1024 해상도로 변경 + 기본 회전
    wlr-randr --output $OUTPUT --mode 1280x1024 --transform normal
    echo "Switched to 1280x1024 with normal rotation."
fi
