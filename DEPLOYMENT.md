# 배포 및 개발 환경 가이드

## 동작 모드 한눈에 보기

| 구분 | Mac Dev | Pi Dev (현재) | Pi Prod |
|------|---------|--------------|---------|
| `ENV_TYPE` | `dev` | `dev` | `prod` |
| YOLO 추론 | ✅ | ✅ | ✅ |
| `/update_count` POST | ❌ 스킵 | ❌ 스킵 | ✅ 전송 |
| STOMP WebSocket | ❌ 스킵 | ❌ 스킵 | ✅ 전송 |
| 디버그 스트림 (8089) | ✅ | ✅ `192.168.10.100:8089` | ❌ |
| FAN/LED 자동제어 | — | ❌ 비활성 | ✅ |
| 레이더 GPIO | ❌ (disabled) | ✅ (GPIO3) | ✅ (GPIO3) |

---

## ENV 변수 레퍼런스

### 핵심 모드

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `ENV_TYPE` | `prod` | `dev` = POST/STOMP 스킵, 디버그 스트림 ON |
| `SENSOR_MODE` | `both` | `camera` / `radar` / `both` |
| `FUSION_MODE` | `confirm` | `gating` / `confirm` (`SENSOR_MODE=both`일 때) |

### 센서 소스 (주로 dev에서 변경)

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `CV_SOURCE` | `ffmpeg` | `ffmpeg` / `video` / `image` |
| `CV_SOURCE_PATH` | — | video/image 경로 |
| `RADAR_SOURCE` | `gpio` | `gpio` / `keyboard` / `file` / `disabled` |
| `RADAR_MOCK_FILE` | `/tmp/radar_tick` | file 소스 트리거 파일 |

### 융합 파라미터

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `RADAR_GPIO_PIN` | `3` | BCM 핀 번호 |
| `RADAR_HOLDTIME` | `3.0` | 레이더 활성 유지 시간(초) |
| `RADAR_FALLBACK_INTERVAL` | `15.0` | 레이더 무신호 시 폴링 주기(초) |
| `CONFIRM_WINDOW` | `5.0` | confirm 모드 확인 윈도우(초) |
| `CONFIRM_HITS` | `2` | confirm 모드 감지 횟수 |
| `DEBUG_STREAM_PORT` | `8089` | 디버그 스트림 포트 |

### SENSOR_MODE 전환 예시

```bash
# 카메라만 (레이더 무시)
SENSOR_MODE=camera

# 레이더만 (YOLO 추론 없음, 초고속)
SENSOR_MODE=radar

# 둘다 — gating: 레이더 활성 시만 카운트
SENSOR_MODE=both FUSION_MODE=gating

# 둘다 — confirm: 레이더 후 카메라 2연속 확인 (기본)
SENSOR_MODE=both FUSION_MODE=confirm
```

---

## Mac 개발 환경

### 최초 실행 (패키지 자동 설치, 5~10분)

```bash
cd /Users/my/app/sbms-pi
./run_dev_mac.sh                     # 테스트 이미지 자동 생성
./run_dev_mac.sh ~/sample.jpg        # 이미지 지정
./run_dev_mac.sh ~/sample.mp4        # 영상 지정
```

브라우저: **http://localhost:8089**
- 왼쪽: 카메라 스트림 + YOLO 박스
- 오른쪽 위: 스카이뷰 히트맵 (발 위치 도트)
- 오른쪽 아래: 실시간 상태 JSON

### 레이더 시뮬레이션 (Mac)

```bash
# keyboard 모드: 터미널에서 'r' + Enter
RADAR_SOURCE=keyboard ./run_dev_mac.sh

# file 모드: 다른 터미널에서 touch
RADAR_SOURCE=file ./run_dev_mac.sh
touch /tmp/radar_tick   # 트리거
```

### venv 재설치 (패키지 오류 시)

```bash
rm -rf ~/.cache/sbms-cv-env
./run_dev_mac.sh
```

---

## Pi 배포

### Pi 현재 설정

| 항목 | 값 |
|------|-----|
| SSH | `ssh admin@192.168.10.100` |
| hostname | `sola-1` |
| 코드 경로 | `/home/admin/gunpo/docker/cv/cv_ffmpeg.py` |
| venv | `/home/admin/gunpo-ori/venv` |
| 서비스 | `cv2_ffmpeg.service` |
| 현재 ENV_TYPE | `dev` |

### cv_ffmpeg.py 단일 파일 배포 (빠름)

```bash
# 1. 백업
ssh admin@192.168.10.100 "cp /home/admin/gunpo/docker/cv/cv_ffmpeg.py /home/admin/gunpo/docker/cv/cv_ffmpeg.py.bak"

# 2. 전송
scp docker/cv/cv_ffmpeg.py admin@192.168.10.100:/home/admin/gunpo/docker/cv/cv_ffmpeg.py

# 3. 재시작
ssh admin@192.168.10.100 "sudo systemctl restart cv2_ffmpeg.service"

# 4. 로그 확인
ssh admin@192.168.10.100 "journalctl -f --no-pager -u cv2_ffmpeg.service"
```

### 전체 코드 배포 (git pull)

```bash
ssh admin@192.168.10.100 "
  cd /home/admin/gunpo &&
  git pull github dev-mac &&
  sudo systemctl restart cv2_ffmpeg.service main_ctl
"
```

### 롤백

```bash
ssh admin@192.168.10.100 "
  cp /home/admin/gunpo/docker/cv/cv_ffmpeg.py.bak /home/admin/gunpo/docker/cv/cv_ffmpeg.py &&
  sudo systemctl restart cv2_ffmpeg.service
"
```

---

## Pi 모드 전환

### Dev → Prod 전환

```bash
ssh admin@192.168.10.100 "
  sed -i 's/ENV_TYPE=dev/ENV_TYPE=prod/' /home/admin/gunpo/docker/.env &&
  sudo systemctl restart cv2_ffmpeg.service
"
```

prod 전환 시:
- POST/STOMP 전송 재개
- 디버그 스트림(8089) 종료
- FAN/LED 자동제어 활성

### Prod → Dev 전환

```bash
ssh admin@192.168.10.100 "
  sed -i 's/ENV_TYPE=prod/ENV_TYPE=dev/' /home/admin/gunpo/docker/.env &&
  sudo systemctl restart cv2_ffmpeg.service
"
```

---

## 로그 모니터링

```bash
# 실시간 로그
ssh admin@192.168.10.100 "journalctl -f --no-pager -u cv2_ffmpeg.service"

# 최근 50줄
ssh admin@192.168.10.100 "journalctl -n 50 --no-pager -u cv2_ffmpeg.service"

# 에러만
ssh admin@192.168.10.100 "journalctl --no-pager -u cv2_ffmpeg.service -p err"

# 디버그 스트림 상태 (dev 모드)
curl http://192.168.10.100:8089/state.json
```

---

## 서비스 전체 목록

| 서비스 | 역할 | venv | 스크립트 |
|--------|------|------|----------|
| `cv2_ffmpeg` | 카메라/레이더 감지 | `gunpo-ori/venv` | `gunpo/docker/cv/cv_ffmpeg.py` |
| `main_ctl` | 통합 제어 (LED/FAN/API) | `gunpo-ori/venv` | `gunpo/docker/main_ctl.py` |
| `button_short_trigger` | 버튼 입력 처리 | `gunpo-ori/venv` | `gunpo/button_short_trigger.py` |
| `gunpo-network-watchdog` | 네트워크 감시/재시작 | `gunpo/venv` | `gunpo/docker/services/network_watchdog.py` |

전체 재시작:
```bash
ssh admin@192.168.10.100 "sudo systemctl restart cv2_ffmpeg main_ctl button_short_trigger gunpo-network-watchdog"
```

전체 상태:
```bash
ssh admin@192.168.10.100 "systemctl is-active cv2_ffmpeg main_ctl button_short_trigger gunpo-network-watchdog"
```
