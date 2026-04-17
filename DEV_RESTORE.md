# 개발 환경 복구 절차 (sola-1 Pi)

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
ssh admin@192.168.10.100 'sudo systemctl stop main_ctl button_short_trigger cv2_ffmpeg gunpo-network-watchdog'
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
```

없으면 추가:
```bash
ssh admin@192.168.10.100 '
  grep -q "POWER_CONTROL_MODE" /home/admin/gunpo/docker/.env || echo "POWER_CONTROL_MODE=relay" >> /home/admin/gunpo/docker/.env
  grep -q "ENV_TYPE" /home/admin/gunpo/docker/.env || echo "ENV_TYPE=dev" >> /home/admin/gunpo/docker/.env
'
```

> **주의**: `ENV_TYPE=dev` 설정 시 FAN 자동제어(온도 기준) 및 LED 스케줄 제어가 비활성화됩니다.

---

## 5. 서비스 시작
```bash
ssh admin@192.168.10.100 'sudo systemctl start main_ctl button_short_trigger cv2_ffmpeg gunpo-network-watchdog'
```

상태 확인:
```bash
ssh admin@192.168.10.100 'systemctl is-active main_ctl button_short_trigger cv2_ffmpeg gunpo-network-watchdog'
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
| `gunpo-network-watchdog` | `gunpo/venv` | `gunpo/docker/services/network_watchdog.py` |

> `/home/admin/gunpo/venv` 는 현재 미존재. 서비스 파일 수정 불필요.

---

## 로그 확인
```bash
ssh admin@192.168.10.100 'tail -f /home/admin/gunpo/docker/logs/app.log'
```
