# 듀얼 모델 성능 분석 및 개선 계획서

> 작성: 2026-05-01  
> 대상: sola-1 (Raspberry Pi 5) / cv2_ffmpeg 서비스  
> 목적: 교통약자 파인튜닝 모델 추가 후 FPS 저하 원인 분석 및 최적화

---

## 1. 현황 (베이스라인)

### 실측 데이터 (2026-05-01)

| 항목 | 단일 모델 (이전) | 듀얼 모델 (현재) |
|------|----------------|----------------|
| FPS | ~3~4 fps | **1.9 fps** |
| 추론 시간/프레임 | ~200~280 ms | **440~560 ms** |
| 모델 수 | 1 (yolo11n.pt) | 2 (yolo11n + mobility) |
| 장치 | Pi 5 CPU | Pi 5 CPU |

### 아키텍처 (현재)

```
RTSP cam → [매 프레임] yolo11n 추론 (person 카운트)
         → [매 프레임] mobility 추론 (휠체어/목발)  ← 병목
```

---

## 2. 문제 분석

### 원인

```
1프레임 처리 시간 = yolo11n 추론(~250ms) + mobility 추론(~250ms) = ~500ms
→ 1000ms / 500ms = 2fps (이론값)
→ 실측 1.9fps (오버헤드 포함)
```

### 교통약자 감지 특성

- 휠체어/목발 보행자는 빠르게 움직이지 않음
- 수초(3~5초) 단위 감지로 충분 (즉각 반응 불필요)
- → **매 프레임 mobility 추론은 과잉**

---

## 3. 개선 방안: N-프레임 스킵

### 개념

```
매 프레임: yolo11n만 실행  → 인원 카운트 유지 (빠른 반응)
매 N프레임: mobility도 실행 → 교통약자 감지 (수초 단위)
```

### 예상 효과

| N값 | mobility 추론 주기 | 예상 FPS | CPU 추가 부하 |
|-----|------------------|----------|-------------|
| 3 | ~1.5초 | ~2.7 fps | +33% |
| 5 | ~2.5초 | ~3.2 fps | +20% |
| 8 | ~4초   | ~3.6 fps | +12% |

**권장: N=5** (2.5초 간격, 실용적 감지 주기)

---

## 4. 구현 코드 (즉시 적용 가능)

### 4-1. 상수 추가 (모델 로딩 블록 하단)

```python
# ── 교통약자 추론 주기 설정 ──────────────────────────────────
MOBILITY_INFER_INTERVAL = int(os.getenv("MOBILITY_INFER_INTERVAL", "5"))
_mobility_frame_counter = 0
_last_mobility_found: list = []
```

### 4-2. infer_once 함수 교체

```python
def infer_once(frame, state: AppState):
    global _mobility_frame_counter, _last_mobility_found

    t0 = time.time()
    h, w = frame.shape[:2]
    scale = 1.0
    if w > INFER_WIDTH:
        scale = INFER_WIDTH / w
        frame_resized = cv2.resize(frame, (INFER_WIDTH, int(h * scale)))
    else:
        frame_resized = frame

    # ── 메인 모델: 인원 감지 (매 프레임) ──────────────────────
    results = model.predict(frame_resized, conf=0.4, imgsz=INFER_WIDTH, verbose=False)
    elapsed = time.time() - t0
    state.fps_ewma = 0.1 * (1.0 / elapsed if elapsed > 0 else 0.0) + 0.9 * state.fps_ewma
    state.last_inference_ms = elapsed * 1000

    boxes = []
    for box in results[0].boxes.data:
        x1, y1, x2, y2, conf, cls_id = box.tolist()
        x1, y1, x2, y2 = map(int, (x1, y1, x2, y2))
        if scale < 1.0:
            x1, y1, x2, y2 = int(x1/scale), int(y1/scale), int(x2/scale), int(y2/scale)
        if int(cls_id) != 0:
            continue
        bw, bh = x2 - x1, y2 - y1
        if bw < 10 or bh < 20:
            continue
        if bh / bw < 0.2 or bh / bw > 4.0:
            continue
        boxes.append((x1, y1, x2, y2))

    annotated = results[0].plot()
    if scale < 1.0:
        annotated = cv2.resize(annotated, (w, h))

    # ── 교통약자 모델: N프레임마다 1회 추론 ──────────────────
    _mobility_frame_counter += 1
    if _mobility_frame_counter >= MOBILITY_INFER_INTERVAL:
        _mobility_frame_counter = 0
        mob_model = mobility_model if mobility_model is not None else model
        mob_results = mob_model.predict(frame_resized, conf=0.45, imgsz=INFER_WIDTH, verbose=False)
        found = []
        for box in mob_results[0].boxes.data:
            _, _, _, _, _, cls_id = box.tolist()
            cls_id = int(cls_id)
            if mobility_model is not None:
                kr = {0: "휠체어", 1: "목발"}.get(cls_id)
            else:
                cname = mob_model.names.get(cls_id, "").lower()
                kr = MOBILITY_LABEL_KR.get(cname) if cname in MOBILITY_AID_CLASSES else None
            if kr and kr not in found:
                found.append(kr)
        _last_mobility_found = found
        if found:
            logger.info(f"[교통약자 감지] {found}")

    logger.info(f"감지된 인원 수: {len(boxes)}")
    return boxes, annotated, _last_mobility_found
```

### 4-3. .env 환경변수 (선택)

```bash
# 기본값 5 (2.5초 주기), 낮출수록 빠른 감지 / 높을수록 FPS 향상
MOBILITY_INFER_INTERVAL=5
```

---

## 5. 적용 절차

```bash
# 1. cv_ffmpeg.py 수정 (섹션 4 코드 적용)
# 2. sola-1에 배포
scp docker/cv/cv_ffmpeg.py sola-tunnel:/home/admin/gunpo/docker/cv/cv_ffmpeg.py

# 3. 재시작
ssh sola-tunnel 'sudo systemctl restart cv2_ffmpeg'

# 4. FPS 검증
ssh sola-tunnel 'curl -s http://localhost:8089/state.json'
# 기대값: fps ≥ 3.0, last_inference_ms ≤ 340ms
```

---

## 6. 디버깅 테스트 절차

### 6-1. sola-1에서 YouTube 영상으로 서비스 테스트

```bash
# 1. YouTube 영상 다운로드 (sola-1 기준, yt-dlp 필요)
ssh sola-tunnel '/home/admin/.local/bin/yt-dlp \
  --no-playlist -f "best[height<=480][ext=mp4]/best[height<=480]" \
  -o /home/admin/data/test_wheelchair.mp4 \
  "https://www.youtube.com/watch?v=kd87waN2k3U"'

# 2. RTSP_URL을 파일 경로로 임시 변경
ssh sola-tunnel "sed -i 's|RTSP_URL=.*|RTSP_URL=/home/admin/data/test_wheelchair.mp4|' ~/gunpo/docker/.env"
ssh sola-tunnel 'sudo systemctl restart cv2_ffmpeg'

# 3. 로그 모니터 (교통약자 감지 확인)
ssh sola-tunnel 'sudo journalctl -u cv2_ffmpeg -f | grep 교통약자'
# 기대: [교통약자 감지] ['휠체어']

# 4. FPS 확인
ssh sola-tunnel 'curl -s http://localhost:8089/state.json'

# 5. 복원
ssh sola-tunnel "sed -i 's|RTSP_URL=.*|RTSP_URL=rtsp://localhost:8554/cam|' ~/gunpo/docker/.env"
ssh sola-tunnel 'sudo systemctl restart cv2_ffmpeg'
```

---

### 6-2. 로컬 PC 디버그 이미지 생성 (gen_debug_heatmap.py)

로컬에서 영상을 추론하여 **bbox + 클래스명** 디버그 이미지를 프레임 단위로 저장합니다.  
`tools/gen_debug_heatmap.py` 참조.

#### 준비

```bash
pip install ultralytics pillow opencv-python

# 테스트 영상 (sola-1에서 복사)
scp sola-tunnel:/home/admin/data/test_wheelchair.mp4 ~/Downloads/test_wheelchair.mp4
```

#### 실행 (단일 모델 — 교통약자만)

```bash
python tools/gen_debug_heatmap.py \
  --model ~/Downloads/best.pt \
  --video ~/Downloads/test_wheelchair.mp4 \
  --out ~/Downloads/debug_wheelchair
```

#### 실행 (듀얼 모델 — 사람 + 교통약자 동시)

```bash
python tools/gen_debug_heatmap.py \
  --model ~/Downloads/best.pt \
  --person-model /path/to/yolo11n.pt \
  --video ~/Downloads/test_wheelchair.mp4 \
  --out ~/Downloads/debug_dual
```

#### 출력 예시

| 파일 | 내용 |
|------|------|
| `debug_0001.jpg` | 감지 프레임 (bbox + 클래스명 + confidence) |
| `heatmap_cumulative.jpg` | 전체 영상 누적 감지 히트맵 |

- 사람 bbox: **파란색** (`person`)
- 휠체어 bbox: **주황색** (`휠체어`)
- 목발 bbox: **초록색** (`목발`)

#### 폰트 요구사항

한글 렌더링에 `맑은 고딕` 사용:
- Windows: `C:/Windows/Fonts/malgun.ttf` (자동)
- Linux: `sudo apt install fonts-nanum && fc-cache -fv`
  → `_KR_FONT_PATH = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"` 로 변경

---

## 7. 벤치마크 체크리스트

### 기능 검증

- [ ] 휠체어 영상 → `[교통약자 감지] ['휠체어']` 로그 출력
- [ ] 목발 영상 → `[교통약자 감지] ['목발']` 로그 출력
- [ ] 일반인 → 교통약자 감지 없음, 인원 카운트 정상
- [ ] 빈 화면 → count=0, 교통약자 없음

### 성능 검증 (N=5 적용 후)

- [ ] `fps ≥ 3.0`
- [ ] `last_inference_ms ≤ 340ms`
- [ ] mobility 감지 누락 없음 (2.5초 내 응답)

### MODE=prod 전환 전 확인

- [ ] 오탐(false positive) 5% 이하
- [ ] 미탐(false negative) 10% 이하
- [ ] 24시간 연속 구동 안정성 확인

---

## 8. 향후 개선 로드맵

| 단계 | 내용 | 예상 효과 |
|------|------|----------|
| **Phase 2** (현재) | N=5 프레임 스킵 적용 | FPS 1.9→3.2 |
| **Phase 3** | OpenVINO INT8 변환 (mobility 모델) | 추론 250ms→60ms |
| **Phase 4** | 두 모델 동시 스레드 실행 | FPS 3.2→4+ |
| **Phase 5** | Person Re-ID (ByteTrack) | 재방문자 판단 가능 |

### OpenVINO 변환 (Colab)

```python
from ultralytics import YOLO
model = YOLO('/content/runs/mobility_yolo11n/weights/best.pt')
model.export(format='openvino', imgsz=416, int8=True)
# → best_openvino_model/ 폴더 생성
# Pi에서: model = YOLO('best_openvino_model/')
```
