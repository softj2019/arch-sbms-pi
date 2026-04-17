# 개발 환경 복구 절차 (sola-1 Pi)

> 배포 방식 전체 가이드 → [DEPLOYMENT.md](./DEPLOYMENT.md)

## 전제 조건
- Pi SSH: `ssh admin@192.168.10.100`
- 작업 디렉토리: `/home/admin/gunpo` (브랜치: `dev-new`)
- Git remote: `https://github.com/softj2019/arch-sbms-pi.git`

---

## 1. SSH 연결 확인
```bash
ssh admin@192.168.10.100 'echo connected'
```

---

## 2. 서비스 중지
```bash
ssh admin@192.168.10.100 'sudo systemctl stop main_ctl button_short_trigger cv2_ffmpeg radar_ctl gunpo-network-watchdog'
```

---

## 3. 코드 최신화 (origin dev-new 기준)
```bash
ssh admin@192.168.10.100 'cd /home/admin/gunpo && git pull github dev-new'
```

---

## 4. .env 설정 확인 및 적용
`/home/admin/gunpo/docker/.env` 에 아래 항목 확인:

```env
POWER_CONTROL_MODE=relay
ENV_TYPE=dev
CAMERA_ENABLED=true        # false: RTSP/YOLO 연결 생략
RADAR_ENABLED=true         # false: 레이더 API 전송 생략
RADAR_GPIO_PIN=4           # RCWL-0516 OUT → GPIO4 (PIN7)
RADAR_SOURCE=disabled      # cv2_ffmpeg 내부 레이더 비활성 (radar_ctl 단독 사용)
```

없으면 추가:
```bash
ssh admin@192.168.10.100 '
  grep -q "POWER_CONTROL_MODE" /home/admin/gunpo/docker/.env || echo "POWER_CONTROL_MODE=relay" >> /home/admin/gunpo/docker/.env
  grep -q "ENV_TYPE" /home/admin/gunpo/docker/.env || echo "ENV_TYPE=dev" >> /home/admin/gunpo/docker/.env
  grep -q "CAMERA_ENABLED" /home/admin/gunpo/docker/.env || echo "CAMERA_ENABLED=true" >> /home/admin/gunpo/docker/.env
  grep -q "RADAR_ENABLED" /home/admin/gunpo/docker/.env || echo "RADAR_ENABLED=true" >> /home/admin/gunpo/docker/.env
  grep -q "RADAR_SOURCE" /home/admin/gunpo/docker/.env || echo "RADAR_SOURCE=disabled" >> /home/admin/gunpo/docker/.env
'
```

> **주의**: `ENV_TYPE=dev` 설정 시 FAN 자동제어(온도 기준) 및 LED 스케줄 제어가 비활성화됩니다.
> `CAMERA_ENABLED=false` 이면 RTSP 연결 시도 자체를 하지 않습니다.
> `RADAR_ENABLED=true` 이면 dev 모드여도 `/update_count` API 호출합니다.

---

## 5. 서비스 시작
```bash
ssh admin@192.168.10.100 'sudo systemctl start main_ctl button_short_trigger cv2_ffmpeg radar_ctl gunpo-network-watchdog'
```

상태 확인:
```bash
ssh admin@192.168.10.100 'systemctl is-active main_ctl button_short_trigger cv2_ffmpeg radar_ctl gunpo-network-watchdog'
```

---

## 6. 릴레이 ON/OFF 테스트
```bash
# ON
ssh admin@192.168.10.100 'cd /home/admin/gunpo/docker && /home/admin/gunpo-ori/venv/bin/python3 -c "
import sys, RPi.GPIO as GPIO
sys.path.insert(0, \".\")
GPIO.setmode(GPIO.BCM); GPIO.setwarnings(False)
from devices.relay_board import relay_on, relay_is_on
relay_on(26); relay_on(20)
print(\"LED:\", \"ON\" if relay_is_on(26) else \"OFF\")
print(\"FAN:\", \"ON\" if relay_is_on(20) else \"OFF\")
"'

# OFF
ssh admin@192.168.10.100 'cd /home/admin/gunpo/docker && /home/admin/gunpo-ori/venv/bin/python3 -c "
import sys, RPi.GPIO as GPIO
sys.path.insert(0, \".\")
GPIO.setmode(GPIO.BCM); GPIO.setwarnings(False)
from devices.relay_board import relay_off, relay_is_on
relay_off(26); relay_off(20)
print(\"LED:\", \"ON\" if relay_is_on(26) else \"OFF\")
print(\"FAN:\", \"ON\" if relay_is_on(20) else \"OFF\")
"'
```

---

## 7. 서비스 파일 기준 (변경 금지)

| 서비스 | venv | 스크립트 |
|------|------|------|
| `main_ctl` | `gunpo-ori/venv` | `gunpo/docker/main_ctl.py` |
| `button_short_trigger` | `gunpo-ori/venv` | `gunpo/button_short_trigger.py` |
| `cv2_ffmpeg` | `gunpo-ori/venv` | `gunpo/docker/cv/cv_ffmpeg.py` |
| `radar_ctl` | `gunpo-ori/venv` | `gunpo/docker/radar_ctl.py` |
| `gunpo-network-watchdog` | `gunpo/venv` | `gunpo/docker/services/network_watchdog.py` |

> `/home/admin/gunpo/venv` 는 현재 미존재. 서비스 파일 수정 불필요.

---

## 8. 레이더 센서 배선 (RCWL-0516)

| 센서 핀 | Pi 핀 | GPIO |
|--------|-------|------|
| VIN | PIN4 | 5V |
| GND | PIN6 | GND |
| OUT | PIN7 | GPIO4 |

---

## 로그 확인
```bash
ssh admin@192.168.10.100 'tail -f /home/admin/gunpo/docker/logs/app.log'
```
