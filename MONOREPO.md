# SBMS-PI 파일 분석 및 최적 모노레포 구조

> 기준: sola-1 (192.168.10.109) 실제 운영 상태 분석  
> 작성: 2026-04-13

---

## 1. 현재 파일 운영 상태 비교

```
╔══════════════════════════════════════════════════════════════════════════════════╗
║              sola-1  /home/admin/gunpo/docker/  파일 운영 상태 분석            ║
╠══════════════════════════════════════════════════════════════════════════════════╣
║  [★ 운영중]  [△ 조건부]  [✕ 미사용/레거시]                                    ║
╠══════════════════════╦═════════════════════════════════════════════════════════╣
║  systemd 직접 실행   ║  서비스 상태                                            ║
╠══════════════════════╬═════════════════════════════════════════════════════════╣
║  ★ main_ctl.py       ║  ACTIVE  ← Flask(5000) + STOMP + 8개 스레드             ║
║  ★ network_watchdog  ║  ACTIVE  ← 네트워크 장애 감시 / 자동 재부팅             ║
║  ★ start_browser.py  ║  DISABLED (air.service) ← Chromium 키오스크             ║
║  △ cv_ffmpeg.py      ║  INACTIVE (cv2_ffmpeg.service) ← YOLO 인원 감지         ║
║  △ boot_report.py    ║  INACTIVE (one-shot) ← 부팅 시 1회 실행                 ║
║  △ wlr.service       ║  INACTIVE (one-shot) ← 해상도/회전 적용 후 종료         ║
║  ✕ wayvnc.service    ║  FAILED  ← VNC 서버 (설정 오류)                         ║
╠══════════════════════╬═════════════════════════════════════════════════════════╣
║  main_ctl 의존 모듈  ║  역할                                                   ║
╠══════════════════════╬═════════════════════════════════════════════════════════╣
║  ★ logging_handler   ║  로깅 설정                                               ║
║  ★ stomp_client      ║  STOMP 발행 (/api/iot/overview)                         ║
║  ★ stomp_rep_client  ║  STOMP 구독 (/api/iot/request) + cv_req 참조            ║
║  ★ tapo_on           ║  LED/팬 Tapo 장치 제어                                  ║
║  ★ network_probe     ║  네트워크 상태 수집                                      ║
║  ★ network_resilience║  재부팅 판단 / 장애 로그                                 ║
║  ★ websocket_endpoint║  WebSocket URL 선택 / 연결                               ║
║  ★ ws_health         ║  WebSocket 헬스 체크                                    ║
║  ★ stop_brower.py    ║  subprocess 호출 (main_ctl line 437)                    ║
╠══════════════════════╬═════════════════════════════════════════════════════════╣
║  cv 모듈             ║  역할                                                   ║
╠══════════════════════╬═════════════════════════════════════════════════════════╣
║  △ cv/cv_ffmpeg.py   ║  RTSP → YOLOv8 인원 감지 (cv2_ffmpeg 비활성 시 대기)   ║
║  △ cv/cv_yolo.py     ║  YOLO 모델 로드/추론                                    ║
║  △ cv/cv_req.py      ║  CV 결과 → STOMP 발행                                  ║
║  ✕ cv/cv_mpeg.py     ║  UNUSED ← cv_ffmpeg 이전 버전 (레거시)                 ║
╠══════════════════════╬═════════════════════════════════════════════════════════╣
║  주기 실행           ║  역할                                                   ║
╠══════════════════════╬═════════════════════════════════════════════════════════╣
║  △ daily_health      ║  cron 매일 06:00 ← 헬스리포트 STOMP 발행               ║
╠══════════════════════╩═════════════════════════════════════════════════════════╣
║  미사용 / 레거시 파일 (삭제 또는 legacy/ 이동 권장)                            ║
╠════════════════════════════════════════════════════════════════════════════════╣
║  root/                                                                         ║
║  ✕ adboard_ctl.py    ← 광고판 제어 (별도 시스템, 미연결)                       ║
║  ✕ gpio_status.py    ← etc/gpio_status.py 중복                                ║
║  ✕ init.py           ← etc/init.py 중복                                       ║
║  ✕ ipcheck.py        ← 단독 IP 확인 유틸 (network_probe로 대체됨)             ║
║  ✕ get_wanip.py      ← 단독 WAN IP 확인 유틸 (network_probe로 대체됨)         ║
║  ✕ lcd_status.py     ← LCD 상태 (미연결)                                       ║
║  ✕ opencv.py         ← OpenCV 테스트                                           ║
║  ✕ opencv-dummy.py   ← OpenCV 더미 테스트                                      ║
║  ✕ opencv_mp4.py     ← MP4 재생 테스트                                         ║
║  ✕ opencv_nonegui.py ← OpenCV 비GUI 테스트                                     ║
║  ✕ rts485Status.py   ← etc/rts485Status.py 중복                               ║
║  ✕ screenStatus.py   ← etc/screenStatus.py 중복                               ║
║  ✕ tapo_fan.py       ← tapo_on.py에 통합 가능 (단독 스크립트)                 ║
║  ✕ tapo_info.py      ← Tapo 정보 조회 유틸 (단독)                             ║
║  ✕ tapo_p110.py      ← P110 전력 측정 유틸 (단독)                             ║
║  ✕ youtube_.py       ← etc/youtube_.py 중복                                   ║
║                                                                                ║
║  etc/ (전체 레거시 / 개발 테스트용)                                            ║
║  ✕ etc/cv_deep.py    ← YOLO 딥러닝 실험용                                     ║
║  ✕ etc/dled.py       ← LED 직접 제어 테스트                                   ║
║  ✕ etc/get_ip.py     ← IP 조회 유틸                                            ║
║  ✕ etc/gpio_status.py← GPIO 상태 테스트                                       ║
║  ✕ etc/gpiotest.py   ← GPIO 테스트                                             ║
║  ✕ etc/gpiotest2.py  ← GPIO 테스트 v2                                         ║
║  ✕ etc/init.py       ← 초기화 스크립트                                         ║
║  ✕ etc/led30.py      ← LED 30개 제어 테스트                                   ║
║  ✕ etc/opencv-dummy.py← OpenCV 더미                                           ║
║  ✕ etc/opencv_mp4.py ← MP4 테스트                                              ║
║  ✕ etc/opencv_strem.py← RTSP 스트림 테스트                                    ║
║  ✕ etc/rts485Status.py← RS485 상태 테스트                                     ║
║  ✕ etc/screenStatus.py← 화면 상태 테스트                                      ║
║  ✕ etc/short.py      ← 단순 유틸                                               ║
║  ✕ etc/tplink_onvif.py← ONVIF 카메라 테스트 (tapo로 대체)                    ║
║  ✕ etc/youtube_.py   ← YouTube 재생 테스트                                    ║
╠════════════════════════════════════════════════════════════════════════════════╣
║  통계: 운영 ★ 9개 / 조건부 △ 8개 / 미사용 ✕ 33개  (총 50개)                 ║
╚════════════════════════════════════════════════════════════════════════════════╝
```

---

## 2. 최적 모노레포 구조

```
╔══════════════════════════════════════════════════════════════════════════════════╗
║                   SBMS-PI 최적 모노레포 구조 (제안)                            ║
╠══════════════════════════════════════════════════════════════════════════════════╣
║  목표: 운영 파일만 루트에 / 장치별 모듈화 / 토큰 탐색 비용 최소화              ║
╚══════════════════════════════════════════════════════════════════════════════════╝

  /home/admin/gunpo/
  │
  ├── docker/                          ← 운영 코드 루트
  │   │
  │   ├── core/                        ← 핵심 제어 (main_ctl 의존 모듈)
  │   │   ├── main_ctl.py              ★ Flask + STOMP 허브
  │   │   ├── logging_handler.py       ★ 로깅
  │   │   ├── websocket_endpoint.py    ★ WS URL 선택
  │   │   ├── ws_health.py             ★ WS 헬스
  │   │   ├── stomp_client.py          ★ STOMP 발행
  │   │   ├── stomp_rep_client.py      ★ STOMP 구독
  │   │   ├── network_probe.py         ★ 네트워크 상태
  │   │   └── network_resilience.py    ★ 재부팅 판단
  │   │
  │   ├── devices/                     ← 장치 제어 모듈
  │   │   ├── tapo_on.py               ★ LED/Fan Tapo 제어 (통합)
  │   │   └── tapo_p110.py             △ P110 전력 모니터 (선택)
  │   │
  │   ├── cv/                          ← 컴퓨터 비전
  │   │   ├── __init__.py
  │   │   ├── cv_ffmpeg.py             △ RTSP → YOLO 인원 감지
  │   │   ├── cv_yolo.py               △ YOLO 모델
  │   │   └── cv_req.py                △ CV 결과 발행
  │   │
  │   ├── services/                    ← 서비스 진입점
  │   │   ├── start_browser.py         △ Chromium 키오스크
  │   │   ├── stop_brower.py           ★ 브라우저 종료 (main_ctl 호출)
  │   │   ├── network_watchdog.py      ★ 네트워크 감시 데몬
  │   │   ├── boot_report.py           △ 부팅 리포트 (one-shot)
  │   │   └── daily_health_report.py   △ 일일 헬스 (cron)
  │   │
  │   ├── config/                      ← 설정 파일
  │   │   ├── .env                     설정값
  │   │   └── .env_custom              커스텀 오버라이드
  │   │
  │   ├── logs/                        ← 로그 (gitignore)
  │   ├── run/                         ← 런타임 상태 (gitignore)
  │   │
  │   └── legacy/                      ← 레거시 (다음 배포 시 삭제)
  │       ├── adboard_ctl.py
  │       ├── cv/cv_mpeg.py
  │       ├── tapo_fan.py
  │       ├── tapo_info.py
  │       └── etc/                     (전체 이동)
  │
  ├── install/                         ← 설치/배포 스크립트
  │   ├── setup.sh                     신규 정류장 초기화
  │   ├── git_pull.sh                  자동 업데이트
  │   └── systemd/                     서비스 파일 모음
  │       ├── main_ctl.service
  │       ├── cv2_ffmpeg.service
  │       ├── air.service
  │       ├── wlr.service
  │       ├── boot-report.service
  │       └── gunpo-network-watchdog.service
  │
  ├── tools/                           ← 관리 도구 (로컬 실행용)
  │   ├── deploy_from_local.sh         25개 정류장 배포
  │   ├── check_all_devices.sh         전체 상태 확인
  │   └── generate_report.sh          리포트 생성
  │
  ├── requirements.txt
  ├── ARCHITECTURE.md                  ← 아키텍처 문서
  ├── MONOREPO.md                      ← 이 파일
  └── README.md

  ────────────────────────────────────────────────────────
  현재 → 목표 디렉토리 이동 요약
  ────────────────────────────────────────────────────────
  docker/*.py (운영)    →  docker/core/ 또는 docker/services/
  docker/etc/*          →  docker/legacy/ (정리 후 삭제)
  docker/cv/cv_mpeg.py  →  docker/legacy/
  docker/tapo_*.py      →  docker/devices/
  install/*.service     →  install/systemd/
  *.sh (루트)           →  tools/

  ────────────────────────────────────────────────────────
  토큰 효율화 효과
  ────────────────────────────────────────────────────────
  Before: docker/ 에 50개 .py 혼재 → 탐색 시 전체 스캔 필요
  After:  core/(9) devices/(2) cv/(4) services/(5) legacy/(33)
          → 디렉토리명만으로 목적 파악, 탐색 범위 80% 감소
          → legacy/ 는 gitignore 또는 별도 브랜치로 분리 가능
```

---

## 3. 즉시 적용 가능한 개선 사항

| 우선순위 | 항목 | 효과 |
|---------|------|------|
| 즉시 | `etc/` 전체 → `legacy/` 이동 | 탐색 노이즈 33개 제거 |
| 즉시 | 루트 중복 파일 삭제 (gpio_status, rts485Status 등) | 중복 8개 제거 |
| 단기 | `core/`, `devices/`, `services/` 디렉토리 분리 | 모듈 경계 명확화 |
| 단기 | wayvnc.service 오류 수정 또는 비활성화 | FAILED 서비스 정리 |
| 중기 | `legacy/` → 별도 브랜치 분리 후 삭제 | 리포 사이즈 최적화 |
