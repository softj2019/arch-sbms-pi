# 재방문자 / 동일인 판단 방법 리서치

> 버스 정류장 교통약자 감지 시스템 (`cv_ffmpeg.py`) 적용 검토용  
> 현재 환경: Raspberry Pi 5, YOLO11n, CPU 추론

---

## 1. 현재 구조의 한계

```
매 프레임 독립 predict() → count(boxes) → POST
```

- 동일인이 10초 동안 서 있어도 매 프레임 "새로운 사람"으로 처리
- 재진입(잠깐 화면 밖→다시 진입)을 새 방문자로 오인 가능
- count가 0→1 전환될 때만 교통약자 이벤트 발생 → 재진입 시 누락

---

## 2. 방법별 비교

### 방법 A: YOLO 내장 트래킹 (ByteTrack / BoT-SORT)

| 항목 | 내용 |
|------|------|
| 원리 | IOU + Kalman Filter로 프레임 간 박스 매칭, `track_id` 부여 |
| API | `model.track(frame, persist=True, tracker="bytetrack.yaml")` |
| track_id | 동일인이면 연속 프레임에서 같은 ID 유지 |
| Pi 적합성 | ⭐⭐⭐⭐ (추가 모델 없음, CPU 오버헤드 약 10~20%) |
| 단점 | 화면에서 벗어났다 재진입 시 새 ID 부여 (단기 occlusion은 버퍼로 커버) |

```python
# 현재 (predict)
results = model.predict(frame_resized, conf=0.4, imgsz=INFER_WIDTH)

# 트래킹 적용
results = model.track(frame_resized, conf=0.4, imgsz=INFER_WIDTH,
                      persist=True, tracker="bytetrack.yaml")

# track_id 추출
for box in results[0].boxes:
    if box.id is not None:
        track_id = int(box.id.item())
        cls_id = int(box.cls.item())
        # cls_id == 0 → person
```

**ByteTrack vs BoT-SORT 차이:**
- `bytetrack.yaml`: 속도 우선, Pi 권장
- `botsort.yaml`: Re-ID 임베딩 포함 → 재진입 ID 유지율 높음, GPU 필요

---

### 방법 B: IoU 기반 수동 트래킹 (SORT-lite)

| 항목 | 내용 |
|------|------|
| 원리 | 현재 프레임 박스와 이전 프레임 박스의 IOU 계산 → 임계값 이상이면 동일인 |
| 의존성 | scipy.optimize (헝가리안 알고리즘) |
| Pi 적합성 | ⭐⭐⭐⭐⭐ (가장 가벼움) |
| 단점 | 빠른 움직임, 겹침 상황에서 ID 스왑 발생 |

```python
from scipy.optimize import linear_sum_assignment
import numpy as np

def iou(boxA, boxB):
    xA = max(boxA[0], boxB[0]); yA = max(boxA[1], boxB[1])
    xB = min(boxA[2], boxB[2]); yB = min(boxA[3], boxB[3])
    inter = max(0, xB - xA) * max(0, yB - yA)
    areaA = (boxA[2]-boxA[0]) * (boxA[3]-boxA[1])
    areaB = (boxB[2]-boxB[0]) * (boxB[3]-boxB[1])
    return inter / (areaA + areaB - inter + 1e-6)
```

---

### 방법 C: Person Re-ID (외형 특징 매칭)

| 항목 | 내용 |
|------|------|
| 원리 | 사람 crop 이미지에서 외형 임베딩 추출 → 코사인 유사도로 동일인 판단 |
| 모델 | OSNet-x0.25 (경량), MobileNet Re-ID |
| Pi 적합성 | ⭐⭐ (추론 1회당 50~150ms 추가, 다중 인원 시 부담) |
| 장점 | 화면에서 사라졌다 재진입해도 동일인 인식 가능 |
| 단점 | 별도 모델 로딩, 야외/역광 환경에서 정확도 저하 |

---

### 방법 D: 색상 히스토그램 기반 경량 Re-ID

| 항목 | 내용 |
|------|------|
| 원리 | 상반신/하반신 HSV 히스토그램 → 유사도 비교 |
| 의존성 | OpenCV만 사용 (추가 모델 없음) |
| Pi 적합성 | ⭐⭐⭐⭐ |
| 단점 | 유사한 색상 옷 착용 시 오인식, 조명 변화에 취약 |

```python
def color_histogram(crop):
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    h_hist = cv2.calcHist([hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
    return cv2.normalize(h_hist, h_hist).flatten()

def similarity(h1, h2):
    return cv2.compareHist(h1, h2, cv2.HISTCMP_CORREL)  # -1 ~ 1
```

---

## 3. 재방문자 카운팅 전략

### 전략 1: 신규 track_id 집계 (단기 체류 카운팅)

```python
seen_ids = set()  # 세션 내 등장한 track_id 집합

for box in results[0].boxes:
    if box.id is None: continue
    tid = int(box.id.item())
    if tid not in seen_ids:
        seen_ids.add(tid)
        new_visitor_count += 1
        logging.info(f"[TRACK] 신규 방문자 track_id={tid}, 누적={new_visitor_count}")
```

### 전략 2: 화면 진입/이탈 이벤트

```python
active_ids = set()

def on_frame(track_ids):
    entered = track_ids - active_ids   # 새로 진입
    exited  = active_ids - track_ids   # 이탈
    active_ids.update(entered)
    active_ids -= exited
    return len(entered), len(exited)
```

### 전략 3: 교통약자 버튼 연동

- 버튼 누름 이벤트 발생 시점의 `track_id`를 기록
- 동일 `track_id`가 재감지되면 "동일인 재요청"으로 처리 (새 이벤트 억제 또는 별도 로깅)

---

## 4. Pi 환경 추천 구현 순서

```
Phase 1: YOLO 내장 ByteTrack 적용 (model.track)
         → track_id로 현재 count 대체, ID 기반 신규 진입만 이벤트 발생
         예상 추가 오버헤드: CPU +15%, 메모리 +20MB

Phase 2: seen_ids 기반 신규 방문자 누적 카운팅
         → 버스 도착 시간대별 교통약자 통계 수집 가능

Phase 3 (선택): 색상 히스토그램 Re-ID로 단기 재진입 동일인 처리
                (5~30초 내 재진입 → 같은 사람으로 판단, 이벤트 미중복 발생)
```

---

## 5. 참고 성능 벤치마크 (Raspberry Pi 5 기준 추정)

| 방법 | 추가 지연 | 메모리 | 추천 |
|------|-----------|--------|------|
| predict만 (현재) | 0ms | 기준 | - |
| ByteTrack | +10~20ms | +20MB | ✅ Phase 1 |
| IoU 수동 SORT | +2~5ms | +1MB | ✅ 대안 |
| 색상 히스토그램 Re-ID | +5~15ms | +5MB | ✅ Phase 3 |
| OSNet Re-ID | +80~200ms | +100MB | ⚠️ 부하 큼 |
| BoT-SORT (Re-ID 포함) | +50~100ms | +80MB | ⚠️ GPU 권장 |

---

*작성일: 2026-04-30*
