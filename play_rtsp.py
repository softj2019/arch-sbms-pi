#!/usr/bin/env python3
"""
RTSP 스트림 재생기
사용법: python3 play_rtsp.py [url]
"""

import cv2
import sys

# RTSP URL
RTSP_URL = sys.argv[1] if len(sys.argv) > 1 else "rtsp://192.168.10.100:8554/cam"

print(f"🎥 RTSP 재생 중: {RTSP_URL}")
print("ESC 누르면 종료\n")

# RTSP 스트림 열기
cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)

if not cap.isOpened():
    print("❌ RTSP 스트림 열기 실패!")
    sys.exit(1)

# 버퍼 크기 설정 (지연 감소)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

frame_count = 0
try:
    while True:
        ret, frame = cap.read()

        if not ret:
            print("❌ 프레임 수신 실패")
            break

        # 프레임 표시
        frame_count += 1
        cv2.putText(frame, f"Frame: {frame_count}", (10, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        cv2.imshow('RTSP Stream', frame)

        # ESC (27) 누르면 종료
        if cv2.waitKey(1) & 0xFF == 27:
            break

except KeyboardInterrupt:
    print("\n중단됨")
finally:
    print(f"✓ 종료 (총 {frame_count}프레임)")
    cap.release()
    cv2.destroyAllWindows()
