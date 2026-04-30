# Pi 보드 결선도 전체

## Raspberry Pi 4B — J8 GPIO 핀맵

```
         3V3 전원  (1) ●  ● (2)  5V 전원   ← RCWL VIN (빨강)
    I2C SDA GPIO2  (3) ●  ● (4)  5V 전원
  ⚠ I2C SCL GPIO3  (5) ●  ● (6)  GND       ← RCWL GND (검정)  ※현재 OUT 연결 중 → 이동 필요
         GPIO4  (7) ●  ● (8)  GPIO14 (UART TX)
           GND  (9) ●  ● (10) GPIO15 (UART RX)
        GPIO17 (11) ●  ● (12) GPIO18        ← ✅ OUT 이동 권장
        GPIO27 (13) ●  ● (14) GND
        GPIO22 (15) ●  ● (16) GPIO23
       3V3 전원 (17) ●  ● (18) GPIO24
        GPIO10 (19) ●  ● (20) GND
         GPIO9 (21) ●  ● (22) GPIO25
        GPIO11 (23) ●  ● (24) GPIO8
           GND (25) ●  ● (26) GPIO7
         GPIO0 (27) ●  ● (28) GPIO1
         GPIO5 (29) ●  ● (30) GND
         GPIO6 (31) ●  ● (32) GPIO12
        GPIO13 (33) ●  ● (34) GND
        GPIO19 (35) ●  ● (36) GPIO16
        GPIO26 (37) ●  ● (38) GPIO20        ← LED 릴레이(26), FAN 릴레이(20)
           GND (39) ●  ● (40) GPIO21        ← SPARE 릴레이(21)
```

---

## 현재 결선 (⚠ GPIO3 문제)

```
Raspberry Pi 4B                        RCWL-0516
┌─────────────────────────┐           ┌───────────────────┐
│ PIN4  (5V)     ──────────────────────► VIN  (전원 5V)   │
│ PIN6  (GND)    ──────────────────────► GND  (접지)      │
│ PIN5  (GPIO3)  ──────────────────────► OUT  (감지신호)  │ ← ⚠ I2C SCL 충돌
│ PIN3  (GPIO2)  ── 미연결                                │
└─────────────────────────┘           └───────────────────┘

⚠ GPIO3(BCM3) = I2C1 SCL 전용 핀
  → 커널이 예약해서 edge detect 등록 불가
  → "Failed to add edge detection" 오류 발생
```

---

## 수정 결선 (✅ GPIO17 권장)

```
Raspberry Pi 4B                        RCWL-0516
┌─────────────────────────┐           ┌───────────────────┐
│ PIN4  (5V)     ──────────────────────► VIN  (전원 5V)   │
│ PIN6  (GND)    ──────────────────────► GND  (접지)      │
│ PIN11 (GPIO17) ──────────────────────► OUT  (감지신호)  │ ← ✅ 변경
│ PIN5  (GPIO3)  ── 미연결 (OUT선 제거)                   │
└─────────────────────────┘           └───────────────────┘

변경 작업:
1. OUT 선(주황)을 PIN5 → PIN11 으로 이동
2. .env에 RADAR_GPIO_PIN=17 추가
```

---

## 릴레이 보드 결선

```
Raspberry Pi 4B                        릴레이 보드
┌─────────────────────────┐           ┌───────────────────┐
│ PIN37 (GPIO26) ──────────────────────► CH1  LED 전원    │
│ PIN38 (GPIO20) ──────────────────────► CH2  FAN 전원    │
│ PIN40 (GPIO21) ──────────────────────► CH3  SPARE       │
│ GND            ──────────────────────► GND              │
│ 5V             ──────────────────────► VCC              │
└─────────────────────────┘           └───────────────────┘
```

---

## 전체 보드 블록 다이어그램

```
                    ┌─────────────────────────────────┐
                    │         Raspberry Pi 4B          │
                    │                                  │
  USB Camera ───────┤ USB(/dev/video0)                 │
  (mediamtx RTSP)   │  ↓ rtsp://localhost:8554/cam    │
                    │                                  │
  RCWL-0516 ────────┤ GPIO17(BCM17) ← OUT 이동 후     │
  레이더센서        │ 5V            ← VIN              │
                    │ GND           ← GND              │
                    │                                  │
  릴레이 보드 ──────┤ GPIO26 → LED                     │
                    │ GPIO20 → FAN                     │
                    │ GPIO21 → SPARE                   │
                    │                                  │
  LED 매트릭스 ─────┤ (main_ctl → 릴레이 → LED)        │
  FAN ─────────────┤ (main_ctl → 릴레이 → FAN)        │
                    │                                  │
  LAN/WiFi ─────────┤ 통합제어보드 POST/STOMP           │
                    └─────────────────────────────────┘

  서비스:
  ├─ cv2_ffmpeg   : USB캠 → YOLO → /update_count
  ├─ main_ctl     : API 수신 → LED/FAN 제어
  ├─ button_short : GPIO 버튼 입력 처리
  └─ mediamtx     : USB캠 → RTSP 변환
```

---

## 즉시 조치 사항

| 작업 | 내용 |
|------|------|
| 🔧 물리 작업 | OUT 선을 **PIN5 → PIN11** 로 이동 |
| ⚙ ENV 설정 | `/home/admin/gunpo/docker/.env` 에 `RADAR_GPIO_PIN=17` 추가 |
| 🔄 서비스 재시작 | `sudo systemctl restart cv2_ffmpeg` |
