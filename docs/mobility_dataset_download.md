# 교통약자 감지 YOLO 데이터셋 다운로드 가이드

> Raspberry Pi 5 + YOLO11n 환경에서 휠체어, 목발, 유모차 감지용 데이터셋/모델 다운로드 방법  
> 작성일: 2026-04-30  
> 관련 문서: [mobility_aid_detection_research.md](./mobility_aid_detection_research.md)

---

## 1. HuggingFace — Wheelchair Detection YOLO 모델

### 현황 요약

HuggingFace에서 **wheelchair 전용 YOLO .pt 파일**은 현재(2026-04) 공식 업로드된 것이 확인되지 않음.  
Ultralytics 공식 YOLO11/YOLOv8 모델은 COCO 80-class 기반이며 wheelchair 클래스 미포함.

### 사용 가능한 대안 — 공개 YOLO .pt (직접 curl 가능)

#### YOLO11n COCO pretrained (baseline, person 클래스만)
```bash
# Ultralytics GitHub releases에서 직접 다운로드 (API 키 불필요)
wget https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt
# 또는
curl -L -O https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt
```
- **Source**: https://huggingface.co/Ultralytics/YOLO11
- **주의**: person(class 0) 만 감지 가능, wheelchair 클래스 없음

#### YOLOv8n COCO pretrained
```bash
wget https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt
```
- **Source**: https://huggingface.co/Ultralytics/YOLOv8

### 결론

HuggingFace에서 wheelchair-specific YOLO .pt는 별도 fine-tuning 없이 사용하는 공개 파일이 없음.  
**Roboflow 또는 직접 fine-tune 방법을 사용해야 함** (아래 섹션 참조).

---

## 2. Open Images V7 — fiftyone으로 특정 클래스만 다운로드

### 클래스 이름 확인

Open Images V7의 600 boxable 클래스 중 mobility aid 관련 정확한 클래스명:

| 한국어 | Open Images V7 클래스명 | 포함 여부 |
|--------|------------------------|---------|
| 휠체어 | `Wheelchair` | ✅ 확인됨 |
| 목발 | `Crutch` | ✅ 확인됨 |
| 유모차 | `Baby carriage` | ✅ 확인됨 |
| 보행 보조기 | `Walker` | 미확인 (직접 확인 필요) |

> 클래스명 대소문자 정확히 일치해야 함 (예: `Wheelchair`, not `wheelchair`)

### 설치

```bash
pip install fiftyone
pip install fiftyone-db-ubuntu2204  # Ubuntu/Pi OS
```

### 클래스 존재 여부 먼저 확인

```python
from fiftyone.utils.openimages import get_classes

all_classes = get_classes()

# mobility aid 관련 클래스 필터링
targets = ['wheelchair', 'crutch', 'carriage', 'walker', 'stroller']
mobility_classes = [c for c in all_classes if any(t in c.lower() for t in targets)]
print(mobility_classes)
# 예상 출력: ['Baby carriage', 'Crutch', 'Wheelchair', ...]
```

### Validation set 다운로드 (YOLO export 포함)

```python
import fiftyone as fo
import fiftyone.zoo as foz

# 1. Validation set에서 특정 클래스만 다운로드
dataset = foz.load_zoo_dataset(
    "open-images-v7",
    split="validation",
    classes=["Wheelchair", "Crutch", "Baby carriage"],
    label_types=["detections"],
    only_matching=True,   # 해당 클래스 레이블만 포함 (다른 클래스 어노테이션 제외)
    max_samples=500,      # 필요 시 제한; None이면 전체
)

print(f"다운로드된 샘플 수: {len(dataset)}")
print(dataset.count_sample_tags())

# 2. YOLO format으로 export
dataset.export(
    export_dir="/path/to/yolo_openimages_mobility",
    dataset_type=fo.types.YOLOv5Dataset,
    label_field="ground_truth",
    classes=["Wheelchair", "Crutch", "Baby carriage"],
)
```

### Train set까지 포함하여 다운로드

```python
import fiftyone as fo
import fiftyone.zoo as foz

CLASSES = ["Wheelchair", "Crutch", "Baby carriage"]
EXPORT_DIR = "/path/to/yolo_dataset"

for split in ["train", "validation"]:
    ds = foz.load_zoo_dataset(
        "open-images-v7",
        split=split,
        classes=CLASSES,
        label_types=["detections"],
        only_matching=True,
    )
    ds.export(
        export_dir=f"{EXPORT_DIR}/{split}",
        dataset_type=fo.types.YOLOv5Dataset,
        label_field="ground_truth",
        classes=CLASSES,
    )
    print(f"{split}: {len(ds)} samples exported")
    fo.delete_dataset(ds.name)
```

### 예상 이미지 수 (Validation set 기준)

공식 per-class 통계는 비공개이나, Open Images V7 전체(validation 41,620장, 600 클래스) 기준으로:

| 클래스 | 예상 validation 이미지 수 |
|--------|------------------------|
| `Wheelchair` | 수백 장 (추정 200–600장) |
| `Crutch` | 수십~수백 장 (추정 50–200장) |
| `Baby carriage` | 수백 장 (추정 200–500장) |

> 정확한 수는 위 Python 코드의 `len(dataset)` 출력으로 확인.

**출처**: 
- https://docs.voxel51.com/dataset_zoo/datasets/open_images_v7.html
- https://storage.googleapis.com/openimages/web/download_v7.html

---

## 3. Roboflow Universe — 공개 Wheelchair YOLO 데이터셋

### API 키 없이 다운로드 가능 여부

Roboflow Universe의 **public 데이터셋**은 브라우저에서 직접 zip 다운로드 가능.  
Python SDK 사용 시 무료 계정 API 키 필요 (무료 가입 후 즉시 발급).

> **API 키 없이 사용하는 방법**: 브라우저에서 Dataset > Export > YOLOv8 > Download zip  
> 또는 아래 Python 코드 (무료 API 키 필요, 가입 무료)

### 주요 공개 데이터셋 목록

| 데이터셋 | 이미지 수 | 클래스 | URL |
|---------|---------|--------|-----|
| **MobilityAids / wheelchair-detection** | 9,206 | wheelchair, walker | https://universe.roboflow.com/mobilityaids/wheelchair-detection-hh3io |
| **wheelchair-detection (2458761304)** | 514 | wheelchair | https://universe.roboflow.com/2458761304-qq-com/wheelchair-detection/dataset/1 |
| **wheelchair-stroller (hijsmom)** | ~800 | wheelchair, stroller | https://universe.roboflow.com/hijsmom/wheelchair-stroller-6hfsm |
| **right3 (seokwoolee)** | 4,260 | wheelchair, umbrella, stroller, bike | https://universe.roboflow.com/seokwoolee/right3 |

### Python 다운로드 코드 (무료 API 키 사용)

```python
# pip install roboflow
from roboflow import Roboflow

# 무료 API 키: https://app.roboflow.com/ 가입 후 Settings > API Keys
rf = Roboflow(api_key="YOUR_FREE_API_KEY")

# MobilityAids 9,206장 데이터셋 (가장 규모 큼)
project = rf.workspace("mobilityaids").project("wheelchair-detection-hh3io")
version = project.version(1)
dataset = version.download("yolov8")   # YOLO11과 동일 포맷
```

### Pretrained 모델 다운로드 (Roboflow hosted)

Roboflow Universe의 pretrained 모델은 **Roboflow Hosted API를 통해서만 추론** 가능.  
로컬 .pt 파일 직접 다운로드는 공식 지원하지 않음.  

**대안**: 데이터셋을 다운로드 후 로컬에서 YOLO11n fine-tune (아래 섹션 참조).

---

## 4. 결론 — 가장 빠르게 Pi에서 테스트하는 방법

### 권장: Open Images V7 fiftyone 다운로드 + YOLO11n Fine-tune

이 방법이 **API 키 불필요 + 공식 대규모 데이터 + 직접 YOLO 포맷 export** 조건을 모두 만족.

#### Step 1: 로컬(Mac)에서 데이터 준비

```bash
pip install fiftyone ultralytics
```

```python
import fiftyone as fo
import fiftyone.zoo as foz

CLASSES = ["Wheelchair", "Crutch", "Baby carriage"]

for split in ["train", "validation"]:
    ds = foz.load_zoo_dataset(
        "open-images-v7",
        split=split,
        classes=CLASSES,
        label_types=["detections"],
        only_matching=True,
    )
    ds.export(
        export_dir=f"./mobility_yolo/{split}",
        dataset_type=fo.types.YOLOv5Dataset,
        label_field="ground_truth",
        classes=CLASSES,
    )
    fo.delete_dataset(ds.name)
```

#### Step 2: data.yaml 작성

```yaml
# mobility_aids.yaml
path: ./mobility_yolo
train: train/images
val: validation/images
nc: 3
names:
  0: Wheelchair
  1: Crutch
  2: Baby carriage
```

#### Step 3: Google Colab에서 Fine-tune (GPU 무료)

```python
# Colab에서 실행
from ultralytics import YOLO

model = YOLO("yolo11n.pt")   # COCO pretrained baseline
model.train(
    data="mobility_aids.yaml",
    epochs=100,
    imgsz=640,
    batch=16,
    freeze=10,               # neck+head만 학습 (빠른 수렴)
    project="mobility_aids",
    name="yolo11n_wheelchair",
)
```

#### Step 4: Pi용 OpenVINO export

```bash
yolo export model=runs/detect/yolo11n_wheelchair/weights/best.pt \
  format=openvino imgsz=640 int8=True
```

#### Step 5: Pi에 복사 후 추론

```bash
scp -r runs/detect/yolo11n_wheelchair/weights/best_openvino_model/ \
  admin@192.168.10.100:~/models/wheelchair/
```

```python
from ultralytics import YOLO

model = YOLO("~/models/wheelchair/best_openvino_model/")
results = model.predict(frame, conf=0.4, imgsz=320)
```

### 속도 기대치 (Pi 5 CPU)

| Export 형식 | 예상 FPS (imgsz=320) | 비고 |
|------------|---------------------|------|
| PyTorch .pt | ~5–8 FPS | 개발/테스트용 |
| ONNX | ~12–15 FPS | 균형 |
| OpenVINO INT8 | ~20–25 FPS | **Pi 5 권장** |

---

## 5. 빠른 참조 — curl/wget 직접 다운로드 URL

| 파일 | URL | 용도 |
|------|-----|------|
| `yolo11n.pt` (COCO) | `https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt` | baseline |
| `yolo11n-pose.pt` | `https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n-pose.pt` | pose 간접 감지 |
| `yolov8n.pt` (COCO) | `https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt` | 대안 baseline |

> wheelchair 전용 pretrained .pt의 curl 직접 다운로드 URL은 현재 공개된 것 없음.  
> fiftyone + fine-tune 경로가 유일한 API 키 없는 공식 경로.

---

## 참고 출처

| 항목 | URL |
|------|-----|
| Ultralytics YOLO11 HuggingFace | https://huggingface.co/Ultralytics/YOLO11 |
| FiftyOne Open Images V7 문서 | https://docs.voxel51.com/dataset_zoo/datasets/open_images_v7.html |
| FiftyOne Open Images 통합 가이드 | https://docs.voxel51.com/integrations/open_images.html |
| Open Images V7 공식 다운로드 | https://storage.googleapis.com/openimages/web/download_v7.html |
| Open Images V7 통계 | https://storage.googleapis.com/openimages/web/factsfigures_v7.html |
| Roboflow MobilityAids 데이터셋 | https://universe.roboflow.com/mobilityaids/wheelchair-detection-hh3io |
| Roboflow 다운로드 문서 | https://docs.roboflow.com/datasets/download-a-dataset |
| Roboflow wheelchair 검색 | https://universe.roboflow.com/search?q=class:wheelchair |
| Ultralytics Raspberry Pi 가이드 | https://docs.ultralytics.com/guides/raspberry-pi/ |
