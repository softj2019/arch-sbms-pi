# 교통약자 감지 모델 파인 튜닝 워크플로우

> YOLO11n 기반 휠체어/목발 감지 모델(`mobility_yolo11n_best.pt`) 재학습 절차  
> 최초 작성: 2026-05-06  
> 관련 문서: [mobility_aid_detection_research.md](./mobility_aid_detection_research.md) · [mobility_dataset_download.md](./mobility_dataset_download.md)

---

## 개요

| 항목 | 내용 |
|------|------|
| 목적 | 휠체어 confidence score 향상 (motorcycle 오분류 개선) |
| 베이스 모델 | `mobility_yolo11n_best.pt` (YOLO11n 기반 fine-tune) |
| 학습 서버 | `arch-ai` (RTX 5090 32GB + RTX 3090 24GB, 10.0.0.115) |
| 데이터 | 로컬 `datasets/mobility_aids/` (train 961장 + val 50장) |
| 배포 대상 | `sola-tunnel` → `/home/admin/data/mobility_yolo11n_best.pt` |

### 개선 결과

| 지표 | 이전 모델 | 이번 모델 |
|------|---------|---------|
| mAP50 | 0.35 ~ 0.44 | **0.80** |
| 학습 epoch | 46 (조기 종료) | 150 (완주) |
| freeze | null (전체 학습) | 10 (백본 고정) |
| 학습 시간 | — | ~15분 (RTX 5090) |

---

## 환경

### SSH 호스트 (`~/.ssh/config`)

| 호스트 별칭 | 실제 주소 | 용도 |
|------------|---------|------|
| `arch-ai` | 10.0.0.115 | 학습 서버 (RTX 5090) |
| `sola-tunnel` | archivsoft 경유 ProxyJump | 배포 대상 Pi |

### 경로 구조

```
arch-ai:/home/my/sbms-pi/
├── datasets/
│   └── mobility_aids/
│       ├── dataset.yaml
│       ├── train/
│       │   ├── images/val/   ← 학습 이미지 (961장)
│       │   └── labels/val/   ← 학습 라벨 (961개)
│       └── validation/
│           ├── images/val/   ← 검증 이미지 (50장)
│           └── labels/val/   ← 검증 라벨 (50개)
├── mobility_yolo11n_best.pt  ← 학습 시작점 (이전 모델)
├── yolo11n.pt                ← COCO base 모델
├── train_mobility_v2.py      ← 학습 스크립트
├── train_v2.log              ← 학습 로그
├── train_v2.pid              ← 프로세스 ID
└── runs/
    └── mobility_v2/
        └── weights/
            ├── best.pt       ← 최종 배포 모델
            └── last.pt
```

로컬(Windows) 데이터 원본:
```
D:/home/sbms-saftypole/
├── datasets/mobility_aids/   ← 실제 JPEG 이미지 (Git LFS 아님)
└── runs/
    └── mobility_v2_best.pt   ← arch-ai 학습 결과 백업
```

---

## 데이터셋 동기화

> **주의**: Git LFS 환경에서는 `.pt`와 이미지가 포인터 파일로 저장됨.  
> sola-1의 `datasets/` 경로도 LFS 포인터이므로 **반드시 로컬 원본에서** 전송할 것.

### 1. arch-ai 디렉토리 초기화

```bash
ssh arch-ai "mkdir -p /home/my/sbms-pi/datasets/mobility_aids/train/images/val \
  /home/my/sbms-pi/datasets/mobility_aids/train/labels/val \
  /home/my/sbms-pi/datasets/mobility_aids/validation/images/val \
  /home/my/sbms-pi/datasets/mobility_aids/validation/labels/val \
  /home/my/sbms-pi/runs"
```

### 2. 로컬 → arch-ai 이미지/라벨 전송 (tar pipe)

```bash
# 학습 이미지 (961장)
tar -czf - -C "D:/home/sbms-saftypole/datasets/mobility_aids/train/images/val" . | \
  ssh arch-ai "tar -xzf - -C /home/my/sbms-pi/datasets/mobility_aids/train/images/val/"

# 학습 라벨
tar -czf - -C "D:/home/sbms-saftypole/datasets/mobility_aids/train/labels/val" . | \
  ssh arch-ai "tar -xzf - -C /home/my/sbms-pi/datasets/mobility_aids/train/labels/val/"

# 검증 이미지 (50장)
tar -czf - -C "D:/home/sbms-saftypole/datasets/mobility_aids/validation/images/val" . | \
  ssh arch-ai "tar -xzf - -C /home/my/sbms-pi/datasets/mobility_aids/validation/images/val/"

# 검증 라벨
tar -czf - -C "D:/home/sbms-saftypole/datasets/mobility_aids/validation/labels/val" . | \
  ssh arch-ai "tar -xzf - -C /home/my/sbms-pi/datasets/mobility_aids/validation/labels/val/"
```

> `scp -r` 대신 **tar pipe를 사용**할 것.  
> `scp -r /tmp/dir/` 방식은 Windows `/tmp` 용량 제한으로 전송이 중간에 잘릴 수 있음.

### 3. dataset.yaml 생성 (arch-ai 경로 기준)

```bash
ssh arch-ai "cat > /home/my/sbms-pi/datasets/mobility_aids/dataset.yaml << 'EOF'
names:
  0: Wheelchair
  1: Crutch
nc: 2
path: /home/my/sbms-pi/datasets/mobility_aids
train: train/images/val
val: validation/images/val
EOF"
```

### 4. 이전 모델 전송

```bash
# sola-1의 실제 모델 경로: /home/admin/data/mobility_yolo11n_best.pt
# (runs/ 하위는 Git LFS 포인터이므로 data/ 경로 사용)
scp sola-tunnel:/home/admin/data/mobility_yolo11n_best.pt /tmp/mobility_best.pt
scp /tmp/mobility_best.pt arch-ai:/home/my/sbms-pi/mobility_yolo11n_best.pt
```

### 5. 동기화 확인

```bash
ssh arch-ai "
  echo 'train images:' \$(find /home/my/sbms-pi/datasets/mobility_aids/train/images -name '*.jpg' | wc -l)
  echo 'train labels:' \$(find /home/my/sbms-pi/datasets/mobility_aids/train/labels -name '*.txt' | wc -l)
  echo 'val images:' \$(find /home/my/sbms-pi/datasets/mobility_aids/validation/images -name '*.jpg' | wc -l)
  # 이미지 포맷 확인 (LFS 포인터이면 ASCII text로 표시됨)
  FIRST=\$(ls /home/my/sbms-pi/datasets/mobility_aids/train/images/val/ | head -1)
  file /home/my/sbms-pi/datasets/mobility_aids/train/images/val/\$FIRST
"
```

정상 출력 예시:
```
train images: 961
train labels: 961
val images: 50
filename.jpg: JPEG image data, JFIF standard 1.01 ...
```

---

## ultralytics 설치

```bash
# arch-ai는 Debian externally-managed 환경 → --break-system-packages 필요
ssh arch-ai "pip3 install ultralytics --break-system-packages"

# CUDA 확인
ssh arch-ai "python3 -c 'import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0))'"
```

---

## 학습 스크립트

`arch-ai:/home/my/sbms-pi/train_mobility_v2.py`:

```python
from ultralytics import YOLO

model = YOLO("/home/my/sbms-pi/mobility_yolo11n_best.pt")

results = model.train(
    data="/home/my/sbms-pi/datasets/mobility_aids/dataset.yaml",
    epochs=150,
    patience=30,
    freeze=10,           # 백본 고정, neck+head만 학습 (핵심)
    imgsz=640,
    batch=32,            # RTX 5090 32GB 기준
    device=0,            # GPU0 = RTX 5090
    lr0=0.001,
    lrf=0.01,
    augment=True,
    hsv_h=0.015,
    hsv_s=0.7,
    hsv_v=0.4,
    flipud=0.0,
    fliplr=0.5,
    mosaic=1.0,
    project="/home/my/sbms-pi/runs",
    name="mobility_v2",
    exist_ok=True,
)
```

### freeze=10의 의미

| 레이어 | freeze 적용 여부 | 역할 |
|--------|---------------|------|
| backbone (layer 0~9) | **고정** | 일반 특징 추출 (COCO로 사전 학습) |
| neck (FPN/PAN) | 학습 | 다중 스케일 특징 통합 |
| head (detection) | 학습 | 클래스 예측 |

> 데이터가 1,000장 미만일 때 전체 학습(freeze=null)은 과적합/불안정 → `freeze=10` 권장

---

## 학습 실행

### 백그라운드 실행 (세션 종료 후에도 유지)

```bash
ssh arch-ai "cd /home/my/sbms-pi && nohup python3 train_mobility_v2.py \
  > /home/my/sbms-pi/train_v2.log 2>&1 & \
  echo \$! > /home/my/sbms-pi/train_v2.pid && \
  echo 'PID:' \$(cat /home/my/sbms-pi/train_v2.pid)"
```

### 진행 상황 모니터링

```bash
# 최근 로그 (epoch 번호 + mAP50 확인)
ssh arch-ai "tail -5 /home/my/sbms-pi/train_v2.log"

# 프로세스 생존 확인
ssh arch-ai "ps -p \$(cat /home/my/sbms-pi/train_v2.pid) -o pid,stat,cmd 2>/dev/null || echo '학습 완료/중단'"
```

### 강제 중단

```bash
ssh arch-ai "kill \$(cat /home/my/sbms-pi/train_v2.pid)"
```

---

## 배포

### 1. arch-ai → 로컬 회수

```bash
scp arch-ai:/home/my/sbms-pi/runs/mobility_v2/weights/best.pt /tmp/mobility_v2_best.pt
# 로컬 백업
cp /tmp/mobility_v2_best.pt "D:/home/sbms-saftypole/runs/mobility_v2_best.pt"
```

### 2. sola-1 배포

```bash
scp /tmp/mobility_v2_best.pt sola-tunnel:/home/admin/data/mobility_yolo11n_best.pt
ssh sola-tunnel "sudo systemctl restart cv2_ffmpeg && sleep 2 && \
  sudo systemctl status cv2_ffmpeg | grep Active"
```

### 배포 경로 확인

| 서버 | 경로 | 용도 |
|------|------|------|
| sola-1 | `/home/admin/data/mobility_yolo11n_best.pt` | **운영 모델** (서비스 로드) |
| sola-1 | `/home/admin/gunpo/runs/.../best.pt` | Git LFS 포인터 (무시) |
| 로컬 | `D:/home/sbms-saftypole/runs/mobility_v2_best.pt` | 백업 |

---

## 트러블슈팅

### 이미지가 corrupt로 처리됨

**증상**: `Scanning labels... 0 images, 0 backgrounds, N corrupt`

**원인**: 이미지 파일이 실제 JPEG가 아닌 Git LFS 포인터 (ASCII text)

**확인**:
```bash
file /path/to/image.jpg
# 정상: JPEG image data, JFIF ...
# 비정상: ASCII text  ← LFS 포인터
head -c 30 /path/to/image.jpg
# 비정상 시 출력: version https://git-lfs.github.com/spec/v1
```

**해결**: 로컬 원본(`D:/home/sbms-saftypole/datasets/`)에서 tar pipe로 재전송

---

### pip install 실패 (externally-managed-environment)

**원인**: Debian 12+ 시스템 Python 보호 정책

**해결**:
```bash
pip3 install ultralytics --break-system-packages
```

---

### scp로 대용량 파일 전송 시 일부 누락

**원인**: Windows `/tmp` 경로 용량 제한 or 디렉토리 중첩 (`scp -r /tmp/dir/` → `dest/dir/` 구조)

**해결**: tar pipe 방식 사용
```bash
# X: scp -r /tmp/dir/ dest/  ← 디렉토리 이름 포함되어 중첩 발생
# O: tar pipe
tar -czf - -C /source/dir . | ssh host "tar -xzf - -C /dest/dir/"
```

---

### best.pt 파일이 132 bytes

**원인**: Git LFS 포인터 파일. `runs/` 하위는 LFS로 관리됨.

**해결**: `data/` 경로 사용
```bash
# X: sola-tunnel:/home/admin/gunpo/runs/.../best.pt  (132 bytes, LFS 포인터)
# O: sola-tunnel:/home/admin/data/mobility_yolo11n_best.pt  (5.3MB, 실제 파일)
```

---

## 재학습 시 체크리스트

- [ ] `arch-ai` SSH 접속 확인: `ssh arch-ai "nvidia-smi"`
- [ ] 데이터셋 이미지 포맷 확인: `file train/images/val/*.jpg` → JPEG 확인
- [ ] dataset.yaml `path` 가 arch-ai 절대 경로로 설정됨
- [ ] `freeze=10` 설정 유지
- [ ] `nohup` + `pid` 파일로 백그라운드 실행
- [ ] 학습 완료 후 mAP50 > 0.70 확인
- [ ] `sola-1:/home/admin/data/` 경로에 배포
- [ ] `sudo systemctl restart cv2_ffmpeg` 후 `active (running)` 확인
- [ ] 로컬 `D:/home/sbms-saftypole/runs/` 에 백업 저장

---

## 참고

| 항목 | 내용 |
|------|------|
| 클래스 정의 | `{0: Wheelchair, 1: Crutch}` |
| 데이터 출처 | Open Images V7 (fiftyone) |
| 상세 데이터 가이드 | [mobility_dataset_download.md](./mobility_dataset_download.md) |
| 모델 구조/성능 리서치 | [mobility_aid_detection_research.md](./mobility_aid_detection_research.md) |
| cv_yolo.py 적용 방식 | 두 모델 순차 추론: base YOLO(person 카운트) → mobility 모델(휠체어 감지) |

---

## 현장 데이터 수집 및 파인튜닝 (collect_finetune.py)

> 실제 운영 환경(군포국민체육센터)에서 휠체어 + 사람 동시 감지 순간을 자동 캡처하여  
> 파인튜닝용 데이터셋을 생성하는 운영 절차.

### 수집 스크립트 위치

| 항목 | 경로 |
|------|------|
| 스크립트 | `sola-1:/home/admin/data/collect_finetune.py` |
| 출력 디렉토리 | `sola-1:/home/admin/data/finetune_dataset/` |
| 출력 형식 | `finetune_set_01.zip` ~ `finetune_set_10.zip` (각 100장 + YOLO 라벨) |

### 동작 원리

```
RTSP 스트림 수신 (localhost:8554/cam)
         ↓
교통약자 모델 (conf=0.30) 추론 → wheelchair/crutch 감지
         ↓
사람 모델 (conf=0.30) 추론 → person/bicycle/motorcycle 감지
         ↓
두 모델 동시 감지 + 면적 필터 (20% 초과 제외)
         ↓
5프레임마다 1장 저장 (중복 방지)
         ↓
100장 완성 → ZIP 패키징 → 다음 세트
```

**핵심 파라미터:**

| 파라미터 | 기본값 | 설명 |
|---------|--------|------|
| `--frames` | 100 | 세트당 저장 장수 |
| `--sets` | 10 | 총 세트 수 |
| `--mob-conf` | 0.30 | 교통약자 감지 신뢰도 (수집용 낮게 설정) |
| `--skip` | 5 | N프레임마다 1장 저장 (중복 방지) |
| `AREA_MAX_RATIO` | 0.20 | 화면 20% 초과 물체 오탐 제외 |

### 수집 실행

```bash
# sola-1 접속 (역방향 터널)
ssh sola-tunnel

# 백그라운드 실행 (터미널 종료 후에도 유지)
cd /home/admin/data
nohup python3 collect_finetune.py \
  --rtsp rtsp://localhost:8554/cam \
  > collect_finetune.log 2>&1 &
echo $! > collect_finetune.pid
echo "PID: $(cat collect_finetune.pid)"
```

### 진행 상황 확인

```bash
# 실시간 로그 (세트 번호 + 저장 장수)
ssh sola-tunnel "tail -f /home/admin/data/collect_finetune.log"

# 완성된 ZIP 목록
ssh sola-tunnel "ls -lh /home/admin/data/finetune_dataset/*.zip 2>/dev/null || echo '아직 없음'"

# 프로세스 생존 확인
ssh sola-tunnel "ps -p \$(cat /home/admin/data/collect_finetune.pid) -o pid,stat,cmd 2>/dev/null || echo '수집 완료/중단'"
```

### 수집 현황 (2026-05-06 기준)

| 세트 | 파일명 | 크기 | 상태 |
|------|--------|------|------|
| 01 | `finetune_set_01.zip` | 24 MB | ✅ 완료 |
| 02 | `finetune_set_02.zip` | 24 MB | ✅ 완료 |
| 03 | `finetune_set_03.zip` | 24 MB | ✅ 완료 |
| 04 | `finetune_set_04.zip` | 24 MB | ✅ 완료 |
| 05 | `finetune_set_05.zip` | 24 MB | ✅ 완료 |
| 06 | `finetune_set_06.zip` | 24 MB | ✅ 완료 |
| 07 | `finetune_set_07.zip` | 24 MB | ✅ 완료 |
| 08 | `finetune_set_08.zip` | 24 MB | ✅ 완료 |
| 09 | `finetune_set_09.zip` | 24 MB | ✅ 완료 |
| 10 | `finetune_set_10.zip` | 24 MB | ✅ 완료 |

> **총 1,000장 (100장 × 10세트) 수집 완료** — 모두 실제 운영 환경 현장 데이터

---

## 현장 데이터 → arch-ai 전송 및 학습

> 수집 완료 후 sola-1의 ZIP 파일을 arch-ai로 전송하여 파인튜닝에 추가.

### 1. sola-1 → 로컬 ZIP 회수

```bash
# 로컬에서 실행
mkdir -p "D:/home/sbms-saftypole/datasets/field_data"
for i in $(seq -w 1 10); do
  scp sola-tunnel:/home/admin/data/finetune_dataset/finetune_set_${i}.zip \
    "D:/home/sbms-saftypole/datasets/field_data/"
done
ls "D:/home/sbms-saftypole/datasets/field_data/"
```

### 2. ZIP 압축 해제 + 데이터셋 병합

```bash
# arch-ai에 현장 데이터 디렉토리 생성
ssh arch-ai "mkdir -p /home/my/sbms-pi/datasets/field_data/images /home/my/sbms-pi/datasets/field_data/labels"

# 각 ZIP을 arch-ai로 전송하고 압축 해제
for i in $(seq -w 1 10); do
  scp "D:/home/sbms-saftypole/datasets/field_data/finetune_set_${i}.zip" \
    arch-ai:/home/my/sbms-pi/datasets/field_data/
  ssh arch-ai "cd /home/my/sbms-pi/datasets/field_data && \
    unzip -o finetune_set_${i}.zip -d set_${i} && \
    cp set_${i}/images/*.jpg images/ && \
    cp set_${i}/labels/*.txt labels/"
done

# 전체 장수 확인
ssh arch-ai "echo 'images:' \$(ls /home/my/sbms-pi/datasets/field_data/images | wc -l); \
             echo 'labels:' \$(ls /home/my/sbms-pi/datasets/field_data/labels | wc -l)"
```

### 3. 현장 데이터 dataset.yaml 생성

```bash
ssh arch-ai "cat > /home/my/sbms-pi/datasets/field_data/dataset.yaml << 'EOF'
names:
  0: Wheelchair
  1: Crutch
nc: 2
path: /home/my/sbms-pi/datasets/field_data
train: images
val: images
EOF"
```

### 4. 현장 데이터로 파인튜닝 실행

```bash
ssh arch-ai "cat > /home/my/sbms-pi/train_field_v1.py << 'EOF'
from ultralytics import YOLO

model = YOLO('/home/my/sbms-pi/mobility_yolo11n_best.pt')

results = model.train(
    data='/home/my/sbms-pi/datasets/field_data/dataset.yaml',
    epochs=100,
    patience=20,
    freeze=10,           # 백본 고정 유지
    imgsz=416,           # sola-1 수집 해상도에 맞춤
    batch=32,
    device=0,
    lr0=0.0005,          # 현장 파인튜닝은 낮은 lr
    lrf=0.01,
    augment=True,
    flipud=0.0,
    fliplr=0.5,
    mosaic=0.5,          # 현장 데이터는 mosaic 줄임
    project='/home/my/sbms-pi/runs',
    name='field_v1',
    exist_ok=True,
)
EOF"

ssh arch-ai "cd /home/my/sbms-pi && nohup python3 train_field_v1.py \
  > train_field_v1.log 2>&1 & \
  echo \$! > train_field_v1.pid && \
  echo 'PID:' \$(cat train_field_v1.pid)"
```

### 5. 학습 모니터링 및 배포

```bash
# 로그 확인
ssh arch-ai "tail -10 /home/my/sbms-pi/train_field_v1.log"

# 완료 후 모델 회수 및 배포 (기존 배포 절차와 동일)
scp arch-ai:/home/my/sbms-pi/runs/field_v1/weights/best.pt /tmp/field_v1_best.pt
cp /tmp/field_v1_best.pt "D:/home/sbms-saftypole/runs/field_v1_best.pt"
scp /tmp/field_v1_best.pt sola-tunnel:/home/admin/data/mobility_yolo11n_best.pt
ssh sola-tunnel "sudo systemctl restart cv2_ffmpeg && sleep 2 && \
  sudo systemctl status cv2_ffmpeg | grep Active"
```

### 재수집이 필요한 경우

수집이 중간에 중단되거나 추가 세트가 필요한 경우:

```bash
# 기존 데이터셋 디렉토리 초기화 없이 이어서 실행
ssh sola-tunnel
cd /home/admin/data

# 특정 세트부터 시작 (--sets로 총 세트 수 조정)
nohup python3 collect_finetune.py \
  --sets 5 \
  > collect_finetune_add.log 2>&1 &
```

> **주의**: `finetune_dataset/` 디렉토리를 비우지 않으면 기존 ZIP에 이어서 세트 번호가 부여됨.  
> 기존 ZIP과 번호가 겹치면 덮어씌워지므로 필요 시 기존 파일 백업 후 실행.
