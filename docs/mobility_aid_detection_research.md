# 교통약자 감지 시스템 리서치

> 버스 정류장 교통약자 감지 시스템 적용 검토  
> 현재 환경: Raspberry Pi 5, YOLO11n (CPU only), COCO 80 class 모델  
> 작성일: 2026-04-30

---

## 1. COCO 80 Classes에 교통약자 관련 클래스 포함 여부

### 결론: **포함되지 않음**

COCO 80개 클래스 전체 목록:

| 번호 | 클래스 | 번호 | 클래스 | 번호 | 클래스 |
|------|--------|------|--------|------|--------|
| 1 | person | 28 | umbrella | 55 | cake |
| 2 | bicycle | 29 | handbag | 56 | chair |
| 3 | car | 30 | tie | 57 | couch |
| 4 | motorcycle | 31 | suitcase | 58 | potted plant |
| 5 | airplane | 32 | frisbee | 59 | bed |
| 6 | bus | 33 | skis | 60 | dining table |
| 7 | train | 34 | snowboard | 61 | toilet |
| 8 | truck | 35 | sports ball | 62 | TV |
| 9 | boat | 36 | kite | 63 | laptop |
| 10 | traffic light | 37 | baseball bat | 64 | mouse |
| 11 | fire hydrant | 38 | baseball glove | 65 | remote |
| 12 | stop sign | 39 | skateboard | 66 | keyboard |
| 13 | parking meter | 40 | surfboard | 67 | cell phone |
| 14 | bench | 41 | tennis racket | 68 | microwave |
| 15 | bird | 42 | bottle | 69 | oven |
| 16 | cat | 43 | wine glass | 70 | toaster |
| 17 | dog | 44 | cup | 71 | sink |
| 18 | horse | 45 | fork | 72 | refrigerator |
| 19 | sheep | 46 | knife | 73 | book |
| 20 | cow | 47 | spoon | 74 | clock |
| 21 | elephant | 48 | bowl | 75 | vase |
| 22 | bear | 49 | banana | 76 | scissors |
| 23 | zebra | 50 | apple | 77 | teddy bear |
| 24 | giraffe | 51 | sandwich | 78 | hair drier |
| 25 | backpack | 52 | orange | 79 | toothbrush |
| 26 | ... | 53 | broccoli | 80 | ... |

**교통약자 관련 클래스 포함 여부:**

| 객체 | COCO 포함 여부 | 비고 |
|------|--------------|------|
| 휠체어 (wheelchair) | ❌ 없음 | COCO에 없음 |
| 전동휠체어 (electric wheelchair) | ❌ 없음 | COCO에 없음 |
| 목발 (crutch) | ❌ 없음 | COCO에 없음 |
| 유모차 (stroller/pram) | ❌ 없음 | COCO에 없음 |
| 보행 보조기 (walking frame/walker) | ❌ 없음 | COCO에 없음 |
| 사람 (person) | ✅ 있음 | class 0, 간접 활용 가능 |

> **핵심**: 현재 YOLO11n COCO 모델만으로는 교통약자 특정 감지 불가.  
> person(class 0) 감지 후 추가 로직(pose, 분류기)으로 보완 필요.

**출처**: [Ultralytics COCO Dataset Docs](https://docs.ultralytics.com/datasets/detect/coco/)

---

## 2. 교통약자 감지 전용 데이터셋

### 2-1. 국제 데이터셋

| 데이터셋 | 운영 | 이미지/영상 수 | 클래스 | 형식 | 접근성 |
|----------|------|--------------|--------|------|--------|
| **MobilityAids** (Univ. Freiburg) | 학술 | 17,079 RGB-D 이미지 | 5개: pedestrian, person-in-wheelchair, pushing-wheelchair, crutches, walking-frame | YAML 어노테이션 | 무료 공개 |
| **Roboflow: wheelchair-detection (MobilityAids)** | Roboflow Universe | 9,206 이미지 | wheelchair, walker | YOLO/COCO JSON | 무료, pretrained 모델 포함 |
| **Roboflow: wheelchair-stroller (hijsmom)** | Roboflow Universe | ~800 이미지 | wheelchair, stroller | YOLO | 무료 |
| **Roboflow: right3 (seokwoolee)** | Roboflow Universe | 4,260 이미지 | umbrella, wheelchair, stroller, bike | YOLO | 무료 |
| **Roboflow: Mobility Aids (Nile Walker)** | Roboflow Universe | 미확인 | 다수 mobility aid 클래스 | YOLO | 무료 |
| **Open Images V7** (Google) | Google AI | 9M+ 이미지, 600 클래스 | Wheelchair 포함 (class 확인 필요) | 다양 | 무료 |
| **CROSSROAD Mobility Aid Dataset** (BMVC 2023) | 학술 | 미확인 | 교차로 환경 mobility aid | — | 논문 공개 |

**MobilityAids 클래스 상세:**

| 클래스 ID | 클래스명 | 설명 |
|-----------|---------|------|
| 0 | pedestrian | 일반 보행자 |
| 1 | person_in_wheelchair | 휠체어 탑승자 |
| 2 | pushing_wheelchair | 휠체어 밀어주는 사람 |
| 3 | crutches | 목발 사용자 |
| 4 | walking_frame | 보행 보조기 사용자 |

**출처**: [MobilityAids (arXiv:1708.00674)](https://arxiv.org/abs/1708.00674), [Roboflow Universe - Wheelchair](https://universe.roboflow.com/search?q=class:wheelchair)

### 2-2. 한국 AI Hub 데이터셋

| 데이터셋명 | 데이터셋 번호 | 클래스 | 규모 | 비고 |
|-----------|-------------|--------|------|------|
| **CCTV 추적 영상** | 34124 | 휠체어 이용자, 시각장애인, 유모차 이용자, 아동 등 6종 | 500시간+ 영상 (휠체어 160h, 유모차 60h 등) | 도시철도 역사 내 CCTV, 승인 후 다운로드 |

> AI Hub CCTV 추적 영상 데이터셋은 **버스 정류장 시나리오와 가장 유사한 한국어 환경 데이터**로, 별도 신청/승인 필요.  
> URL: [aihub.or.kr/aidata/34124](https://aihub.or.kr/aidata/34124)

### 2-3. Pascal VOC / Open Images 클래스 현황

| 데이터셋 | Wheelchair | Crutch | Stroller |
|---------|-----------|--------|---------|
| Pascal VOC 2012 (20 classes) | ❌ | ❌ | ❌ |
| Open Images V7 (600 classes) | ✅ Wheelchair 포함 | 확인 필요 | 일부 포함 |
| COCO 2017 (80 classes) | ❌ | ❌ | ❌ |
| COCO-stuff (172 classes) | ❌ | ❌ | ❌ |

---

## 3. 라즈베리파이 5에서 실행 가능한 경량 모델 비교

### 3-1. YOLO 계열 Pi 5 CPU 추론 속도 (imgsz=640)

| 모델 | Export 형식 | 추론 속도 (ms/frame) | FPS | 모델 크기 | mAP50-95 | Pi 적합성 |
|------|------------|---------------------|-----|-----------|-----------|----------|
| **YOLO11n** | PyTorch | 360 ms | 2.8 | 5.4 MB | 39.5 | ⭐⭐ |
| **YOLO11n** | ONNX | 147–157 ms | 6.4–6.8 | 10.5 MB | 39.5 | ⭐⭐⭐ |
| **YOLO11n** | OpenVINO | 81 ms | **12.4** | 10.8 MB | 39.5 | ⭐⭐⭐⭐ |
| **YOLO11n** | MNN | 116 ms | 8.6 | — | 39.5 | ⭐⭐⭐ |
| **YOLO11n** | NCNN | 292 ms | 3.4 | 6.0 MB | 39.5 | ⭐⭐ |
| **YOLO11s** | OpenVINO | ~200 ms | ~5 | 21.5 MB | 47.0 | ⭐⭐⭐ |
| **YOLOv8n** | NCNN | ~83 ms | **~12** | 6.0 MB | 37.3 | ⭐⭐⭐⭐ |
| **YOLOv8n (INT8 양자화)** | TFLite | ~45 ms | **~22** | ~3.5 MB | ~35 | ⭐⭐⭐⭐⭐ |
| **YOLO11n (INT8 양자화)** | — | ~77 ms | **~13** | ~3 MB | ~37 | ⭐⭐⭐⭐ |

> **권장 조합**: YOLOv8n INT8 양자화 (22 FPS, 가장 실용적)  
> OpenVINO + YOLO11n 도 12 FPS로 준수, Ultralytics 공식 지원

### 3-2. 비 YOLO 경량 모델 비교

| 모델 | Pi 5 추론 속도 | FPS | 모델 크기 | mAP (COCO) | Pi 적합성 | 비고 |
|------|--------------|-----|-----------|-----------|----------|------|
| **MobileNet SSD v1** | 93 ms | 10.8 | 6.9 MB | 19.0 | ⭐⭐⭐ | 정확도 낮음 |
| **MobileNet SSD v2** | ~110 ms | ~9 | 16.9 MB | 22.1 | ⭐⭐⭐ | v1보다 정확 |
| **EfficientDet Lite0** | ~130 ms | ~7.7 | 4.4 MB | 26.0 | ⭐⭐⭐ | TFLite 최적화 |
| **EfficientDet Lite2** | ~200 ms | ~5 | 7.5 MB | 33.0 | ⭐⭐ | 균형 모델 |
| **NanoDet-Plus-m** | 빠름 (추정 50–80 ms) | ~15–20 | 1.8 MB (fp16) / 0.98 MB (int8) | 34.1 | ⭐⭐⭐⭐⭐ | **최경량, ARM 최적화** |
| **EdgeYOLO-S** | GPU 권장 | <30 (Jetson) | 중간 | 44.1 | ⭐⭐ | Jetson 타깃, Pi에 부적합 |
| **YOLO-World (YOLOv8s-world)** | ~500 ms+ | <2 | 62 MB+ | 높음 | ⭐ | Open vocab 가능하나 Pi에 과중 |

> **NanoDet-Plus**: Pi 5 CPU에서 가장 빠른 추론 예상, 단 커스텀 클래스 학습 환경이 YOLO보다 복잡  
> **EdgeYOLO**: Jetson AGX Xavier 타깃 설계, Pi에는 적합하지 않음  
> **YOLO-World**: 텍스트 프롬프트 기반 zero-shot 감지 가능하지만 Pi에서 실시간 불가

### 3-3. 추론 속도 총괄 (Pi 5 CPU, 640×640 기준)

```
빠름 ←────────────────────────────→ 느림

NanoDet-Plus   YOLOv8n(INT8)   YOLO11n(OpenVINO)   YOLO11n(ONNX)   YOLO11n(PyTorch)
~15-20 FPS       ~22 FPS            ~12 FPS              ~6.4 FPS         ~2.8 FPS
```

**출처**:
- [Ultralytics Raspberry Pi Guide](https://docs.ultralytics.com/guides/raspberry-pi/)
- [Benchmarking Deep Learning Models for Edge Devices (arXiv:2409.16808)](https://arxiv.org/abs/2409.16808)
- [NanoDet-Plus GitHub](https://github.com/RangiLyu/nanodet)
- [EdgeYOLO (arXiv:2302.07483)](https://arxiv.org/abs/2302.07483)

---

## 4. Transfer Learning / Fine-tuning 가능성

### 4-1. YOLO11n에 wheelchair class 추가 Fine-tune 난이도

| 항목 | 내용 |
|------|------|
| 기본 원리 | COCO pretrained backbone 유지, detection head만 새 class에 맞게 재초기화 |
| 난이도 | ★★☆☆☆ (Ultralytics API 기준 매우 쉬움) |
| backbone 호환성 | 완전 호환 — `model = YOLO('yolo11n.pt'); model.train(data='custom.yaml')` |
| head 처리 | 분류 레이어 자동 재초기화, bbox regression은 pretrained 가중치 유지 |
| GPU 필요 여부 | 학습 시 GPU 권장 (Google Colab 무료 T4 활용 가능), 추론은 CPU OK |

### 4-2. 필요 데이터셋 크기

| 시나리오 | 권장 이미지 수 | 학습 설정 | 예상 mAP |
|---------|-------------|----------|---------|
| 최소 (few-shot, 도메인 유사) | 100–300장 | `freeze=23` (head만 학습) | 40–55% |
| 실용 수준 | 300–1,000장 | `freeze=10` (neck+head 학습) | 60–75% |
| 권장 수준 | 1,000–3,000장 | 전체 fine-tune | 75–85% |
| 고품질 | 3,000장+ + 데이터 증강 | 전체 fine-tune + aug | 85%+ |

> **핵심 인사이트**: YOLO full fine-tune은 소량 데이터에서 성능 저하 발생.  
> 100장 이하는 `freeze=23`으로 head만 학습하거나 **YOLO-Adapter** 방식 권장.  
> YOLO-Adapter는 full fine-tune 대비 최대 **14.9% mAP 향상** (적은 데이터 환경).

### 4-3. Roboflow에서 바로 쓸 수 있는 Pretrained 모델

| 모델/데이터셋 | 이미지 수 | 클래스 | Pretrained 제공 | URL |
|-------------|---------|--------|----------------|-----|
| **MobilityAids / wheelchair-detection** | 9,206 | wheelchair, walker | ✅ 있음 (API) | [링크](https://universe.roboflow.com/mobilityaids/wheelchair-detection-hh3io) |
| **wheelchair-detection (2458761304)** | 514 | wheelchair | ✅ 있음 | [링크](https://universe.roboflow.com/2458761304-qq-com/wheelchair-detection/dataset/1) |
| **wheelchair-stroller (hijsmom)** | ~800 | wheelchair, stroller | 확인 필요 | [링크](https://universe.roboflow.com/hijsmom/wheelchair-stroller-6hfsm) |
| **right3 (seokwoolee)** | 4,260 | wheelchair, umbrella, stroller, bike | 확인 필요 | [링크](https://universe.roboflow.com/seokwoolee/right3) |

> **MobilityAids 9,206장 pretrained 모델**이 가장 즉시 활용 가능.  
> Roboflow API로 바로 추론 가능, YOLO11 포맷으로 export하여 로컬 배포도 가능.

**출처**:
- [Ultralytics Fine-Tuning Guide](https://docs.ultralytics.com/guides/finetuning-guide/)
- [YOLO-Adapter (ScienceDirect)](https://www.sciencedirect.com/science/article/abs/pii/S0925231226005357)
- [WheelPose CHI 2024](https://dl.acm.org/doi/10.1145/3613904.3642555)

---

## 5. 추천 구현 방향

### 5-1. Pi 5 CPU 환경에서 현실적인 접근법

#### 방향 A: Roboflow pretrained 모델 직접 활용 (난이도 ★☆☆☆☆)

```python
# Roboflow MobilityAids 모델을 YOLO11 포맷으로 export 후 로컬 사용
from ultralytics import YOLO

# MobilityAids 데이터셋으로 학습된 모델 로드
model = YOLO("wheelchair_mobilityaids_yolo11n.pt")  # export 후

results = model.predict(frame, conf=0.4, imgsz=320)
for box in results[0].boxes:
    cls = int(box.cls.item())
    # 0: pedestrian, 1: person_in_wheelchair, 2: pushing_wheelchair
    # 3: crutches, 4: walking_frame
    if cls in [1, 2, 3, 4]:  # 교통약자 클래스
        trigger_accessibility_event()
```

| 항목 | 평가 |
|------|------|
| 구현 난이도 | ★☆☆☆☆ |
| 추론 속도 (Pi 5) | YOLO11n ONNX 기준 ~6–12 FPS (imgsz=320 시 ~15 FPS) |
| 클래스 범위 | wheelchair, crutches, walking_frame |
| 유모차 감지 | 별도 데이터셋 필요 |
| Pi 적합성 | ⭐⭐⭐⭐ |

#### 방향 B: YOLO11n Fine-tune (커스텀 클래스 추가, 난이도 ★★★☆☆)

```bash
# 1. Roboflow에서 데이터 다운로드 (wheelchair + stroller 혼합)
# 2. Google Colab에서 학습
yolo detect train \
  model=yolo11n.pt \
  data=mobility_aids.yaml \
  epochs=100 \
  imgsz=640 \
  freeze=10 \
  batch=16

# 3. 학습된 모델 ONNX/OpenVINO export
yolo export model=best.pt format=openvino imgsz=640
```

```yaml
# mobility_aids.yaml 예시
path: ./datasets/mobility_aids
train: images/train
val: images/val
nc: 4
names: ['wheelchair', 'stroller', 'crutches', 'walking_frame']
```

| 항목 | 평가 |
|------|------|
| 구현 난이도 | ★★★☆☆ |
| 클래스 범위 | 완전 커스터마이징 가능 |
| 필요 데이터 | 클래스당 최소 300장 (Roboflow Universe에서 조합 가능) |
| 학습 시간 | Colab T4 기준 약 30분 (100 epochs) |
| Pi 적합성 | ⭐⭐⭐⭐⭐ (학습 후 경량 모델 Pi에서 실행) |

#### 방향 C: Person + Pose Estimation으로 간접 감지 (난이도 ★★☆☆☆)

```python
from ultralytics import YOLO

pose_model = YOLO("yolo11n-pose.pt")  # NCNN export 권장

def classify_mobility_aid(keypoints, bbox):
    """
    키포인트 기반 교통약자 간접 감지
    - 휠체어: 상체 높이 낮음 + 하체 키포인트 불활성
    - 목발: 팔꿈치 좌우 비대칭 + 손목 위치 낮음
    """
    # 좌우 엉덩이 키포인트 (11, 12번) y좌표
    hip_y = (keypoints[11][1] + keypoints[12][1]) / 2
    # 어깨 키포인트 (5, 6번) y좌표
    shoulder_y = (keypoints[5][1] + keypoints[6][1]) / 2
    
    bbox_height = bbox[3] - bbox[1]
    
    # 앉은 자세 감지 (휠체어/유모차 사용자 특징)
    sitting_ratio = (hip_y - shoulder_y) / bbox_height
    if sitting_ratio < 0.3:  # 상체-엉덩이 간격이 좁으면 앉은 자세
        return "possible_wheelchair"
    return "standing"

results = pose_model.track(frame, persist=True, conf=0.4, imgsz=320)
```

| 항목 | 평가 |
|------|------|
| 구현 난이도 | ★★☆☆☆ |
| 추가 모델 필요 | 없음 (yolo11n-pose.pt 사용) |
| 추론 속도 (Pi 5) | ~100–150 ms (NCNN export 시 ~60–80 ms) |
| 정확도 한계 | 간접 추론 — 오탐 가능성 있음 |
| 유모차 감지 | 어려움 (유모차 자체는 person 아님) |
| Pi 적합성 | ⭐⭐⭐ |

### 5-2. 방향별 Pi 적합성 종합 평가

| 접근법 | Pi 5 실시간 가능 | 감지 정확도 | 구현 기간 | 유지보수 | 추천도 |
|--------|---------------|-----------|---------|---------|--------|
| A. Roboflow pretrained | ✅ 가능 (~10 FPS) | 중상 | 1일 | 낮음 | ⭐⭐⭐⭐⭐ |
| B. Fine-tune 커스텀 | ✅ 가능 (~12 FPS) | 높음 | 3–5일 | 중간 | ⭐⭐⭐⭐ |
| C. Pose 간접 감지 | ✅ 가능 (~8 FPS) | 낮음–중간 | 1–2일 | 낮음 | ⭐⭐⭐ |
| YOLO-World zero-shot | ❌ 불가 (<2 FPS) | 높음 | 1일 | 낮음 | ⭐ |
| NanoDet-Plus 커스텀 | ✅ 가능 (~20 FPS) | 중간 | 5–7일 | 높음 | ⭐⭐⭐ |

---

## 6. 결론 및 최종 추천

### 단기 (1–3일): 방향 A 즉시 적용

1. Roboflow Universe에서 **MobilityAids 9,206장 모델** 다운로드
2. YOLO11n 포맷으로 export 후 현재 `cv_ffmpeg.py`에 통합
3. `imgsz=320`으로 낮춰 Pi 5에서 **15+ FPS** 확보
4. OpenVINO export로 추가 최적화 가능

```python
# cv_ffmpeg.py 통합 예시
MOBILITY_CLASSES = {1: "wheelchair", 2: "pushing_wheelchair", 
                    3: "crutches", 4: "walking_frame"}

def is_mobility_aid_user(cls_id):
    return cls_id in MOBILITY_CLASSES
```

### 중기 (1–2주): 방향 B 커스텀 Fine-tune

- Roboflow에서 wheelchair + stroller + crutch 데이터 조합 (총 3,000장 목표)
- AI Hub CCTV 추적 영상 데이터셋 신청 (한국 환경에 최적화)
- Google Colab에서 YOLO11n fine-tune → OpenVINO export → Pi 5 배포

### 데이터 수집 우선순위

| 우선순위 | 데이터소스 | 클래스 | 접근 방법 |
|---------|----------|--------|---------|
| 1 | Roboflow MobilityAids | wheelchair, walker | 즉시 무료 다운로드 |
| 2 | Roboflow right3 | wheelchair, stroller | 즉시 무료 다운로드 |
| 3 | AI Hub CCTV 추적 영상 | 휠체어, 유모차, 시각장애인 | 신청 후 승인 (1–2주) |
| 4 | 직접 촬영 | 버스 정류장 특화 | 현장 수집 |

---

## 참고 문헌 / 출처

| 항목 | URL |
|------|-----|
| COCO Dataset (Ultralytics) | https://docs.ultralytics.com/datasets/detect/coco/ |
| MobilityAids Paper (arXiv) | https://arxiv.org/abs/1708.00674 |
| Roboflow Wheelchair 검색 | https://universe.roboflow.com/search?q=class:wheelchair |
| Roboflow MobilityAids 모델 | https://universe.roboflow.com/mobilityaids/wheelchair-detection-hh3io |
| Roboflow wheelchair+stroller | https://universe.roboflow.com/hijsmom/wheelchair-stroller-6hfsm |
| AI Hub CCTV 추적 데이터셋 | https://aihub.or.kr/aidata/34124 |
| Ultralytics RPi 가이드 | https://docs.ultralytics.com/guides/raspberry-pi/ |
| Edge 기기 벤치마크 (arXiv) | https://arxiv.org/abs/2409.16808 |
| NanoDet-Plus GitHub | https://github.com/RangiLyu/nanodet |
| EdgeYOLO (arXiv) | https://arxiv.org/abs/2302.07483 |
| YOLO-World (CVPR 2024) | https://arxiv.org/abs/2401.17270 |
| Ultralytics Fine-Tune 가이드 | https://docs.ultralytics.com/guides/finetuning-guide/ |
| YOLO-Adapter (ScienceDirect) | https://www.sciencedirect.com/science/article/abs/pii/S0925231226005357 |
| WheelPose CHI 2024 | https://dl.acm.org/doi/10.1145/3613904.3642555 |
| YOLOv10+Faster RCNN 연구 | https://www.sciencedirect.com/science/article/pii/S1110016825009421 |
