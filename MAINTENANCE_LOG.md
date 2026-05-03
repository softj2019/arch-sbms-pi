# 유지보수 로그

## 2026-05-01 - LED 전등 릴레이 자동 점등/소등 고도화

### 문제
- `ENV_TYPE=dev` 환경에서 `schedule_device_control()`이 스케줄 루프를 통째로 스킵
- 릴레이 ON/OFF가 전혀 동작하지 않아 현장에서 LED 전등 자동제어 불가
- 로그에 아무것도 찍히지 않아 원인 파악 어려웠음

### 원인
`main_ctl.py` schedule_device_control() 내부:
```python
if ENV_TYPE == 'dev':
    await asyncio.sleep(3)
    continue   # ← 릴레이 제어 전체 스킵
```

### 해결 (commit: eb18ec6)
- `if ENV_TYPE == 'dev': continue` 블록 제거 (10줄 삭제)
- ENV_TYPE 무관하게 릴레이 자동 점등/소등 실행
- STOMP 연결 시 서버 on/off 시간 적용, 미연결 시 기본값 `17:00`/`04:00` 사용

### 검증
```
INFO - schedule_device_control: [relay] 상태확인 - 현재=OFF, 목표=ON, 설정시간=17:00~04:00
INFO - relay_board: pin 20 → ON (LOW)
INFO - schedule_device_control: LED 전등 ON [relay] (점등시간: 17:00 ~ 04:00)
```
서비스 재시작 직후 17:02에 즉시 릴레이 ON 확인

---

## 2026-05-01 - LED 릴레이 스케줄 동작 로그 추가

### 배경
릴레이가 언제 ON/OFF 됐는지 로그가 없어 현장 문제 진단이 어려움

### 변경 (commit: a241a4a)
`schedule_device_control()`에 `_periodic` 로그 추가 (약 60초마다 출력):
- manual override 중: 남은 시간 출력
- relay 상태 확인: 현재 상태 / 목표 상태 / 설정 시간 출력
- LED ON/OFF 전환 시: 즉시 INFO 로그

### 로그 위치
```
~/gunpo/docker/core/logs/main_ctl/2605/260501.log
```
(journalctl이 아닌 파일 로그)

---

## 2026-05-03 - SSH 역방향 터널 복구 절차 확인

### 증상
`ssh sola-tunnel` 접속 시 `Connection refused` — 터널 포트(20022)는 열려있으나 sola-1 미연결

### 원인
sola-1 재부팅 후 `reverse-tunnel.service` 자동 재연결 실패

### 복구 절차
1. Raspberry Pi Connect로 sola-1 직접 접속
2. 터널 서비스 재시작:
   ```bash
   sudo systemctl restart reverse-tunnel.service
   ```
3. 로컬에서 확인:
   ```bash
   ssh sola-tunnel "echo OK"
   ```

### 서비스명 참고
- 터널: `reverse-tunnel.service` (autossh-tunnel.service 아님)
- SSH: `ssh.service`

---

## 2026-04-20 - main_ctl WebSocket 성능 이슈

### 문제
- radar_ctl: `POST 실패: localhost:5000 Read timed out (10초)`
- main_ctl `/update_count` 응답: **13초** (타임아웃: 10초)

### 원인
**main_ctl.py:1137**
```python
asyncio.run(send_stomp_message("/topic/screen/action", stop_message, PROD_WEBSOCKET_URL))
```
- Flask 핸들러에서 동기적으로 WebSocket 메시지 전송 대기
- WebSocket 연결/전송이 10초 이상 소요

### 원인 분석
1. `show_waiting_message()` - 디스플레이 제어 (1127줄)
2. `asyncio.run()` - WebSocket 연결 (1137줄) ← **병목**
3. 네트워크 지연 또는 수신자 응답 지연

### 복구 기록
**2026-04-20 15:54:01**
```bash
rm -f /tmp/main_ctl.pid
sudo systemctl restart main_ctl.service
```
- PID 파일 잠금 제거로 서비스 정상화
- 그 후 10분 안정적 운영
- 15:56:56 시점에 타임아웃 재발

### 해결책 (2026-04-20 16:00~16:07)

**1단계: 환경설정 분기 확인** ✓
- TERMINAL_ID=1234567, OFFICE_HOSTNAME=1234567 → 개발모드 정상
- DEV_WEBSOCKET_URL 선택 (ws://10.0.0.217:8080/websocket)
- 문제: WebSocket 서버 오프라인 → asyncio.run() timeout

**2단계: smartpole 단독모드 대응** ✓
- main_ctl.py 수정 (3곳):
  - 1137줄: STOP 메시지 전송 → smartpole 스킵
  - 1067줄: power/action 메시지 → smartpole 스킵
  - 235줄: screen/action 메시지 → smartpole 스킵
- 결과: /update_count 응답 **13초 → 23ms**

**3단계: radar_ctl 재시도 로직** ✓
- radar_ctl.py 수정: 최대 3회 재시도 (500ms 간격)
- Flask 초기화 대기 중 Connection refused → 자동 복구

### 최종 상태
| 항목 | 상태 | 응답시간 |
|------|------|---------|
| /update_count | ✅ 정상 | 23ms |
| radar_ctl | ✅ 정상 | 재시도 적용 |
| GPIO 센서 | ✅ 정상 | - |

### 생성된 도구
```bash
/Users/my/app/sbms-pi/tail_logs.sh           # 실시간 로그
/Users/my/app/sbms-pi/repair_main_ctl.sh     # 자동 복구
/Users/my/app/sbms-pi/switch_sensor_mode.sh  # 센서 모드 전환
```

---

## 센서 모드 전환 (2026-04-20 17:07)

### 사용법
```bash
./switch_sensor_mode.sh [모드]

모드:
  radar       - 레이더 센서만 활성
  camera      - 카메라만 활성
  dual        - 둘 다 활성
  status      - 현재 설정 확인
```

### 예시
```bash
# 레이더 → 카메라 전환
./switch_sensor_mode.sh camera

# 현재 설정 확인
./switch_sensor_mode.sh status

# 듀얼 모드
./switch_sensor_mode.sh dual
```

### 동작 방식
1. .env 파일 수정 (RADAR_ENABLED, CAMERA_ENABLED)
2. 서비스 재시작 (radar_ctl, cv2_ffmpeg, main_ctl)
3. 상태 확인

### 현재 상태 (2026-04-20 17:07)
- RADAR_ENABLED: false (비활성)
- CAMERA_ENABLED: true (활성)

---

## cv2_ffmpeg 디버그 모드 (DEBUG STREAM)

### 개요
cv2_ffmpeg는 ENV_TYPE에 따라 실시간 디버그 스트림을 제공합니다.
- **ENV_TYPE=dev**: 디버그 스트림 활성 (YOLO 감지 결과 실시간 표시)
- **ENV_TYPE=prod**: 디버그 스트림 비활성 (성능 최적화)

### 디버그 스트림 접속

**웹 브라우저에서:**
```
http://192.168.10.100:8089
```

**구성:**
- 좌측: 실시간 카메라 MJPEG 스트림 (감지 박스 + 레이더 상태)
- 우측: 성능 지표 및 상태 정보

### 표시 정보

| 항목 | 설명 |
|------|------|
| 객체 박스 | 녹색 사각형 - YOLO로 감지된 사람 |
| 원형 지시자 | 빨강(활성)/회색(비활성) - 레이더 상태 |
| 빨강 테두리 | 1초 이내 레이더 신호 감지 |
| 우측 패널 | FPS, 추론시간, 감지 수, 모드 등 |

### ENV_TYPE 설정

**현재 설정 확인:**
```bash
ssh admin@192.168.10.100 "grep ENV_TYPE /home/admin/gunpo/docker/.env"
```

**디버그 모드 활성화:**
```bash
ssh admin@192.168.10.100 << 'EOF'
  sed -i 's/ENV_TYPE=.*/ENV_TYPE=dev/g' /home/admin/gunpo/docker/.env
  sudo systemctl restart cv2_ffmpeg.service
  sleep 2
  systemctl status cv2_ffmpeg.service --no-pager | grep Active
EOF
```

**성능 모드 (프로덕션):**
```bash
ssh admin@192.168.10.100 << 'EOF'
  sed -i 's/ENV_TYPE=.*/ENV_TYPE=prod/g' /home/admin/gunpo/docker/.env
  sudo systemctl restart cv2_ffmpeg.service
EOF
```

### 성능 차이

| 모드 | CPU 사용 | 메모리 | YOLO 추론 | 디버그 스트림 |
|------|---------|--------|----------|--------------|
| dev | 높음 | +50MB | 동일 | ✅ 활성 |
| prod | 낮음 | 기본 | 동일 | ❌ 비활성 |

### 스트림 성능 최적화

**현재 설정 (cv_ffmpeg.py:512, 518):**
```python
JPEG 품질: 80
프레임 대기: 0.05s (20fps)
```

**빠른 스트림을 원할 경우:**
```
JPEG 품질: 80 → 60 (파일크기 ↓30%)
프레임 대기: 0.05s → 0.033s (20fps → 30fps)
```

### YOLO 감지가 안 될 때 체크리스트

1. **ENV_TYPE=dev 확인**
   ```bash
   ssh admin@192.168.10.100 "grep ENV_TYPE /home/admin/gunpo/docker/.env"
   ```

2. **카메라 입력 확인**
   ```bash
   ssh admin@192.168.10.100 "ffmpeg -f v4l2 -list_formats all -i /dev/video0 2>&1 | head -20"
   ```

3. **YOLO 모델 확인**
   - 모델: yolov8n.pt (Nano, 가장 경량)
   - 위치: /home/admin/data/yolov8n.pt

4. **추론 속도 로그 확인**
   ```bash
   ssh admin@192.168.10.100 "journalctl -u cv2_ffmpeg.service -n 50 | grep -E 'Speed|inference'"
   ```

5. **실시간 테스트**
   - 카메라 앞에서 움직여보기
   - 8089 웹 스트림에서 박스 표시 확인
   - 시간이 걸릴 수 있음 (추론 시간: 350-360ms)
