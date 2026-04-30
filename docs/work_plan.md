# 작업 계획 (2026-04-30 기준)

## 현재 상태

### sola-1 서비스 구성
| 서비스 | 파일 | 상태 |
|--------|------|------|
| main_ctl.service | docker/main_ctl.py | 운영 중 |
| cv2_ffmpeg.service | docker/cv/cv_ffmpeg.py | 운영 중 |
| radar_ctl.service | docker/radar_ctl.py | `time_led` 모드, 17:30~05:30 |

### 완료된 작업
- [x] YOLO11n 모델 업그레이드 (yolov8n → yolo11n.pt)
- [x] cv_ffmpeg: 30fps raw 캡처 스레드 분리 + `/stream_raw` 엔드포인트
- [x] cv_ffmpeg: `results[0].plot()` 내장 오버레이 적용 (custom annotate 제거)
- [x] cv_ffmpeg: `MODE=debug|prod` 환경변수 추가
- [x] cv_ffmpeg: MOBILITY_AID_CLASSES 감지 (휠체어, 목발 등) + debug 시 LED 출력
- [x] radar_ctl: `RADAR_MODE=time_led` 스케줄 모드 추가 (자정 넘김 처리)
- [x] radar_ctl: `_schedule_override` STOMP 런타임 변경 지원 준비
- [x] Open Images V7 교통약자 데이터셋 다운로드 (train 961장 + val 50장, Wheelchair/Crutch)
- [x] Colab 파인튜닝 노트북 생성 (`colab_train_mobility.ipynb`)

---

## 다음 작업 (우선순위 순)

### Phase 1: YOLO11n 교통약자 파인튜닝 ← 현재 진행 중
**목표**: Wheelchair/Crutch 전용 경량 모델 학습

**준비 완료**
- 데이터셋: `datasets/mobility_aids/` (train 961 + val 50)
- zip: `datasets/mobility_aids.zip` (336MB) — Mac 로컬에만 있음
- Colab 노트북: `colab_train_mobility.ipynb`

**남은 절차**
1. `mobility_aids.zip` → Google Drive `sbms-pi/` 폴더에 업로드
2. `colab_train_mobility.ipynb` Colab에서 열기 (런타임: T4 GPU)
3. 노트북 순서대로 실행 (예상 ~1시간)
4. Drive에서 `mobility_yolo11n_best.pt` 다운로드
5. sola-1에 배포:
   ```bash
   scp mobility_yolo11n_best.pt admin@192.168.10.100:/home/admin/gunpo/docker/core/
   ```
6. `.env` 모델 경로 변경 후 cv2_ffmpeg 재시작

**참고**
- Mac 인터넷이 빠르므로 Drive 업로드는 Mac에서
- Colab T4 무료 GPU, 세션 최대 12시간
- 클래스: 0=Wheelchair, 1=Crutch (Baby carriage는 OI V7 미지원으로 제외)

---

### Phase 2: 파인튜닝 모델 배포 및 검증
- cv_ffmpeg `MOBILITY_AID_CLASSES` 클래스명을 파인튜닝 모델 클래스에 맞게 조정
- `MODE=debug`로 sola-1에서 실제 감지 테스트
- `MODE=prod`로 전환 후 최종 배포

---

### Phase 3: Person Re-ID (재방문자 판단) — 선택 사항
- 연구 문서: `docs/person_reid_research.md`
- 권장: YOLO 내장 ByteTrack (`model.track(..., persist=True)`)
- Pi 오버헤드: CPU +15%, 메모리 +20MB
- 구현 전 파인튜닝 모델 안정화 후 진행

---

## 파일 구조 참고

```
sbms-pi/
├── colab_train_mobility.ipynb     # Colab 학습 노트북
├── datasets/
│   └── mobility_aids/             # OI V7 데이터셋 (Mac 로컬)
│       ├── dataset.yaml
│       ├── train/  (961장)
│       └── validation/  (50장)
├── docker/
│   ├── .env                       # MODE=debug, RADAR_MODE=time_led
│   ├── cv/cv_ffmpeg.py
│   ├── main_ctl.py
│   └── radar_ctl.py
├── docs/
│   ├── mobility_aid_detection_research.md
│   ├── mobility_dataset_download.md
│   └── person_reid_research.md
└── scripts/
    └── zip_dataset.sh
```

## sola-1 접속
```bash
ssh admin@192.168.10.100        # 로컬 (동일 라우터)
ssh -p 20022 admin@58.121.142.83  # 역터널 (외부)
```

---

## 유지보수: 역방향 터널 (autossh)

### 구성
- sola-1 → `58.121.142.83:2222` 역터널, 외부 포트 `20022` → sola-1:22
- autossh 프로세스: sola-1에서 수동 실행 (systemd 서비스 없음)

### 역터널 끊김 시 복구

**sola-1에서 재시작:**
```bash
kill $(pgrep autossh)
sleep 2
AUTOSSH_GATETIME=0 autossh -M 0 -f -N \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
  -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=no \
  -i /home/admin/.ssh/id_ed25519 \
  -R 0.0.0.0:20022:localhost:22 my@58.121.142.83 -p 2222
```

**확인:**
```bash
ssh -p 20022 admin@58.121.142.83
```

### ⚠️ GatewayPorts 필수 설정 (원격 서버 1회 적용)

역터널이 재시작해도 외부 접속이 안 될 경우, 원격 서버(`58.121.142.83`)의
`GatewayPorts` 설정이 꺼져 있는 것. **원격 서버에서 1회 적용 필요:**

```bash
# 원격 서버 (58.121.142.83) 에서 실행
echo "GatewayPorts clientspecified" | sudo tee -a /etc/ssh/sshd_config
sudo systemctl restart sshd
```

적용 후 sola-1에서 autossh 재시작하면 외부 접속 정상화됨.

### autossh systemd 서비스 등록 (선택 — 재부팅 후 자동 복구)
```bash
# sola-1에서 실행
sudo tee /etc/systemd/system/autossh-tunnel.service << 'EOF'
[Unit]
Description=AutoSSH Reverse Tunnel
After=network-online.target
Wants=network-online.target

[Service]
User=admin
Environment="AUTOSSH_GATETIME=0"
ExecStart=/usr/lib/autossh/autossh -M 0 -N \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
  -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=no \
  -i /home/admin/.ssh/id_ed25519 \
  -R 0.0.0.0:20022:localhost:22 my@58.121.142.83 -p 2222
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable --now autossh-tunnel.service
```
