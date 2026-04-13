# SBMS-PI 모노레포 구조 개편 세부 수행계획

> 작성: 2026-04-13 | 팀회의 기준 문서  
> 대상: 라즈베리파이 25개 정류장 통합제어 시스템  
> 원칙: **운영 중단 없음 / 각 Phase 독립 롤백 가능**

---

## 현황 요약

```
현재 문제점
─────────────────────────────────────────────────────
  파일 혼재   docker/ 에 운영/레거시/테스트 .py 50개 혼재
  보안 취약   .env 평문 비밀번호, 배포 스크립트 하드코딩
  의존성 불일치 requirements.txt UTF-16, 실제 패키지 2개만 명시
  배포 불안정 25개 IP 하드코딩, 롤백 없음, StrictHostChecking=no
  서비스 오류 wayvnc FAILED, air DISABLED, shim 없음
  CI 느슨함  flake8 복잡도 15, import 실행 검증 없음
```

---

## Phase 0 — 긴급 보안 (Day 1~2)

```
목표: 평문 비밀번호 즉시 격리
─────────────────────────────────────────────────────────────────
  작업 1   docker/.env → .gitignore 추가
  작업 2   .env.example 생성 (키만, 값 없음)
  작업 3   deploy_from_local.sh SSH_ASKPASS 하드코딩 제거
  작업 4   Git 이력에서 .env 삭제 (bfg 또는 filter-branch)
           → 완료 후 25개 Pi 전체 git reset --hard 필요

  리스크    낮음 (운영 코드 변경 없음)
  롤백      git revert 1개 커밋
  완료기준  git log -p -- docker/.env 에 비밀번호 미출력
```

---

## Phase 1 — 레거시 격리 및 의존성 정상화 (Day 3~5)

```
목표: 50개 → 17개 (운영 파일만 docker/ 루트에)
─────────────────────────────────────────────────────────────────
  작업 1   미사용 33개 파일 → docker/legacy/ 이동
           [이동 대상]
           root:  adboard_ctl, gpio_status, init, ipcheck,
                  get_wanip, lcd_status, opencv*.py (4개),
                  rts485Status, screenStatus, tapo_fan,
                  tapo_info, tapo_p110, youtube_
           cv/:   cv_mpeg.py
           etc/:  전체 14개 (디렉토리째 이동)

  작업 2   requirements.txt 재작성
           - UTF-8 재인코딩
           - 실제 운영 의존성 전체 명시:
             flask, websockets, RPi.GPIO, pyserial, psutil,
             python-dotenv, requests, pydantic, tapo,
             opencv-python, ultralytics, torch

  작업 3   .gitignore 보강
           docker/.env, docker/.env_custom, *.log,
           logs_*, report_*.md, debug_*, collect_logs_*.log

  리스크    매우 낮음 (이동 파일 모두 운영 import 없음 검증 완료)
  롤백      git revert
  완료기준  ls docker/*.py | wc -l ≤ 17
            pip install -r requirements.txt --dry-run 성공
            CI py_compile (legacy/ 제외) 통과
            1개 Pi systemctl is-active main_ctl = active
```

---

## Phase 2 — 핵심 디렉토리 분리 (Day 6~10)  ★ 가장 중요

```
목표: 운영 파일을 역할별 서브패키지로 분리
─────────────────────────────────────────────────────────────────
  최종 구조

  docker/
  ├── core/               핵심 제어 모듈 (main_ctl 의존 8개)
  │   ├── main_ctl.py
  │   ├── logging_handler.py
  │   ├── websocket_endpoint.py
  │   ├── ws_health.py
  │   ├── stomp_client.py
  │   ├── stomp_rep_client.py
  │   ├── network_probe.py
  │   └── network_resilience.py
  ├── devices/            장치 드라이버
  │   └── tapo_on.py
  ├── cv/                 컴퓨터 비전 (위치 유지)
  │   ├── cv_ffmpeg.py
  │   ├── cv_yolo.py
  │   └── cv_req.py
  ├── services/           서비스 진입점
  │   ├── network_watchdog.py
  │   ├── boot_report.py
  │   ├── daily_health_report.py
  │   ├── start_browser.py
  │   └── stop_brower.py
  ├── config/
  │   ├── .env
  │   └── .env_custom
  └── legacy/             (Phase 1 완료)

  작업 1   각 서브디렉토리 __init__.py 생성
  작업 2   systemd 서비스 파일 ExecStart 경로 갱신
           main_ctl        → core/main_ctl.py
           network-watchdog → services/network_watchdog.py
           boot-report     → services/boot_report.py
  작업 3   모든 .service 파일에 PYTHONPATH 추가
           Environment=PYTHONPATH=/home/admin/gunpo/docker
  작업 4   하위 호환 shim 파일 생성 (import 안전망)
           docker/logging_handler.py → from core.logging_handler import *
           (다른 모듈도 동일 방식)
  작업 5   cron 경로 갱신
           daily_health_report.py → services/daily_health_report.py

  배포 순서 (무중단)
  ─────────────────────────────────────────────────────
  Step 1   dev 브랜치 작업 + CI 검증
  Step 2   테스트 Pi 1대 수동 배포 → 24시간 관찰
           curl http://localhost:5000/system_info 확인
           STOMP overview 10초 주기 수신 확인
  Step 3   prod merge → CD 자동 배포 (self-hosted runner)
  Step 4   5개씩 그룹 A 배포 → 10분 관찰
  Step 5   5개씩 그룹 B 배포 → 10분 관찰
  Step 6   나머지 15개 (5개×3회)
  Step 7   check_all_devices.sh 전체 확인

  리스크    높음 (import 경로 변경)
  롤백      prod 브랜치 git revert → 자동 배포 재트리거
            긴급: deploy_from_local.sh 이전 커밋 강제 배포
  완료기준  25개 Pi 전체
            · systemctl is-active main_ctl = active
            · curl localhost:5000/system_info 정상
            · STOMP overview 정상 수신
            · LED/팬 제어 정상
```

---

## Phase 3 — 배포 파이프라인 개선 (Day 11~20)

```
목표: 안전하고 관리 가능한 배포 체계 확립
─────────────────────────────────────────────────────────────────
  작업 1   deploy/hosts.txt 분리
           25개 IP 하드코딩 → 파일로 외부화

  작업 2   deploy_from_local.sh 개선
           - --rollback COMMIT_HASH 옵션 추가
           - 배포 후 curl health check 자동화
           - SSH 키 인증 전환 (SSH_ASKPASS 제거)
           경로: deploy/scripts/deploy_from_local.sh

  작업 3   systemd 서비스 중앙 관리
           deploy/systemd/ 에 전체 .service 파일 집중
           install_services.sh 일괄 설치 스크립트

  작업 4   루트 정리
           *.sh → tools/ 또는 deploy/scripts/
           *.log, report_*.md, debug_* → gitignore

  작업 5   wayvnc 정리
           FAILED 원인 수정 또는 systemctl disable

  작업 6   CI 강화
           flake8 max-complexity: 15 → 10
           legacy/ 제외 적용
           운영 파일(core/ devices/ services/ cv/) strict lint

  리스크    낮음 (배포 스크립트 변경은 Pi 운영과 독립)
  롤백      git revert
  완료기준  deploy --rollback 동작 확인
            전체 .service 파일이 deploy/systemd/ 에 존재
            CI max-complexity=10 통과
```

---

## Phase 4 — 최종 완성 (Day 21~30)

```
목표: shim 제거, 태깅, CD 파이프라인 완성
─────────────────────────────────────────────────────────────────
  작업 1   Phase 2 shim 파일 제거
           모든 import가 새 경로 사용 확인 후 삭제

  작업 2   CD 파이프라인 서비스 파일 자동 갱신
           cd.yml에 sudo cp deploy/systemd/*.service + daemon-reload 추가

  작업 3   버전 태깅
           v0.1.0-pre-monorepo  Phase 0 전 스냅샷 (현재)
           v0.8.0               Phase 1 완료
           v0.9.0               Phase 2 완료
           v0.9.5               Phase 3 완료
           v1.0.0               Phase 4 완료

  작업 4   (선택) docker/ → pi/ 디렉토리 리네임
           25개 Pi 경로 전체 변경 필요 → 리스크 대비 이점 낮음
           심볼릭 링크 활용 시 무중단 가능

  완료기준  shim 파일 0개
            git tag v1.0.0
            25개 Pi 48시간 무장애
```

---

## 전체 일정

```
Week 1
  Day 1~2   Phase 0  보안 긴급 패치
  Day 3~5   Phase 1  레거시 격리 + 의존성 정상화

Week 2
  Day 6~10  Phase 2  핵심 디렉토리 분리 ★
             (카나리 배포 → 그룹 배포 → 전체)

Week 3~4
  Day 11~20 Phase 3  배포 파이프라인 개선
  Day 21~30 Phase 4  최종 완성 + v1.0.0 태깅
```

---

## Git 브랜치 전략

```
dev ──┬── feat/monorepo-phase0  → dev → prod
      ├── feat/monorepo-phase1  → dev → prod
      ├── feat/monorepo-phase2  → dev → (카나리 수동) → prod
      ├── feat/monorepo-phase3  → dev → prod
      └── feat/monorepo-phase4  → dev → prod

prod  ← CD 트리거 (self-hosted runner + deploy_from_local.sh)
```

---

## 핵심 리스크 매트릭스

```
┌─────────────────────────────────────┬──────┬──────┬──────────────────────────┐
│ 위험                                │ 확률 │ 영향 │ 대응                     │
├─────────────────────────────────────┼──────┼──────┼──────────────────────────┤
│ Phase 2 import 오류로 main_ctl 미기동│ 중   │ 치명 │ shim 파일 + 카나리 배포  │
│ systemd 서비스 파일 미갱신           │ 높   │ 높   │ install_services.sh 자동화│
│ Git 이력 정리 후 Pi 불일치           │ 중   │ 중   │ 전체 git reset --hard    │
│ 25개 Pi 동시 배포 실패              │ 낮   │ 치명 │ 5개씩 그룹 + 관찰 시간   │
│ cron/systemd 경로 누락              │ 중   │ 중   │ 배포 후 --failed 검증    │
└─────────────────────────────────────┴──────┴──────┴──────────────────────────┘
```

---

## 완료 검증 체크리스트 (최종)

```
Phase 0  □ docker/.env 가 gitignore 처리됨
         □ 배포 스크립트에 평문 비밀번호 없음

Phase 1  □ docker/*.py ≤ 17개
         □ pip install --dry-run 성공
         □ CI py_compile (legacy/ 제외) 통과

Phase 2  □ 전체 25개 Pi:
         □   systemctl is-active main_ctl = active
         □   curl localhost:5000/system_info 정상
         □   STOMP overview 정상
         □   LED/팬 제어 정상
         □   check_all_devices.sh 전체 green

Phase 3  □ deploy --rollback 동작
         □ wayvnc FAILED 해소
         □ CI max-complexity=10 통과

Phase 4  □ shim 파일 0개
         □ git tag v1.0.0
         □ 48시간 무장애 운영
```
