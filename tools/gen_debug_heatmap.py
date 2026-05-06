"""
휠체어/목발 감지 디버그 이미지 생성

사용법:
  # 단일 모델 (교통약자만)
  python tools/gen_debug_heatmap.py --model best.pt --video test.mp4 --out ./debug_out

  # 듀얼 모델 (사람 + 교통약자 동시)
  python tools/gen_debug_heatmap.py --model best.pt --person-model yolo11n.pt --video test.mp4 --out ./debug_out

출력:
  debug_XXXX.jpg          감지 프레임 (bbox + 클래스명 + confidence)
  heatmap_cumulative.jpg  전체 누적 감지 히트맵
"""
import argparse
import sys
import cv2
import numpy as np
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from ultralytics import YOLO

# ── 한글 폰트 ──────────────────────────────────────────────────
_KR_FONT_CANDIDATES = [
    "C:/Windows/Fonts/malgun.ttf",                                      # Windows 맑은 고딕
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",                  # Linux NanumGothic
    "/usr/share/fonts/opentype/nanum/NanumGothic.otf",
]
_KR_FONT_PATH: str | None = None
for _fp in _KR_FONT_CANDIDATES:
    if Path(_fp).exists():
        _KR_FONT_PATH = _fp
        break

_kr_font_cache: dict = {}


def _kr_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if _KR_FONT_PATH is None:
        return ImageFont.load_default()
    if size not in _kr_font_cache:
        _kr_font_cache[size] = ImageFont.truetype(_KR_FONT_PATH, size)
    return _kr_font_cache[size]


def put_kr_text(
    img_bgr: np.ndarray,
    text: str,
    xy: tuple,
    font_size: int = 22,
    color_bgr: tuple = (255, 255, 255),
    bg_color_bgr: tuple | None = None,
) -> np.ndarray:
    """OpenCV BGR 이미지에 한글 텍스트를 Pillow로 렌더링."""
    pil = Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))
    draw = ImageDraw.Draw(pil)
    font = _kr_font(font_size)
    x, y = xy
    color_rgb = color_bgr[::-1]

    if bg_color_bgr is not None:
        bbox = draw.textbbox((x, y), text, font=font)
        pad = 3
        draw.rectangle(
            (bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad),
            fill=tuple(bg_color_bgr[::-1]),
        )
    draw.text((x, y), text, font=font, fill=tuple(color_rgb))
    return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)


# ── 색상 팔레트 ────────────────────────────────────────────────
# BGR
COLOR_PERSON   = (255, 140, 0)   # 파란색 계열  (person)
COLOR_WHEEL    = (0, 120, 255)   # 주황색       (휠체어)
COLOR_CRUTCH   = (0, 220, 100)   # 초록색       (목발)

MOB_CLASS_KR   = {0: "휠체어", 1: "목발"}
MOB_CLASS_CLR  = {0: COLOR_WHEEL, 1: COLOR_CRUTCH}


# ── 박스 그리기 ────────────────────────────────────────────────
def draw_boxes(img: np.ndarray, detections: list, class_kr: dict, class_clr: dict) -> np.ndarray:
    """detections = list of (x1,y1,x2,y2, conf, cls_id)"""
    out = img.copy()
    for x1, y1, x2, y2, conf, cls_id in detections:
        cls_id = int(cls_id)
        label = class_kr.get(cls_id, f"cls{cls_id}")
        color = class_clr.get(cls_id, (128, 128, 128))
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
        text = f"{label} {conf:.2f}"
        ty = max(y1 - 28, 2)
        out = put_kr_text(out, text, (x1 + 2, ty),
                          font_size=22, color_bgr=(255, 255, 255), bg_color_bgr=color)
    return out


# ── 누적 히트맵 ────────────────────────────────────────────────
def accumulate_heat(heat: np.ndarray, detections: list) -> None:
    """boxes 영역을 confidence만큼 heat에 누적."""
    for x1, y1, x2, y2, conf, _ in detections:
        heat[y1:y2, x1:x2] += conf


def save_cumulative_heatmap(heat: np.ndarray, bg_frame: np.ndarray | None,
                             out_path: Path) -> None:
    heat_norm = np.clip(heat / heat.max() * 255, 0, 255).astype(np.uint8)
    heat_color = cv2.applyColorMap(heat_norm, cv2.COLORMAP_JET)

    if bg_frame is not None:
        bg = cv2.resize(bg_frame, (heat_color.shape[1], heat_color.shape[0]))
        overlay = cv2.addWeighted(bg, 0.5, heat_color, 0.6, 0)
    else:
        overlay = heat_color

    overlay = put_kr_text(overlay, "누적 감지 히트맵",
                          (10, 8), font_size=24, color_bgr=(255, 255, 255))
    cv2.imwrite(str(out_path), overlay)
    print(f"누적 히트맵 저장: {out_path}")


# ── 메인 ───────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="교통약자(+사람) 감지 디버그 이미지 생성",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--model", required=True, help="교통약자 모델 경로 (best.pt)")
    p.add_argument("--person-model", default=None,
                   help="사람 감지 모델 경로 (yolo11n.pt). 지정하면 듀얼 모드 활성화")
    p.add_argument("--video", required=True, help="테스트 영상 경로")
    p.add_argument("--out", required=True, help="출력 디렉토리")
    p.add_argument("--conf", type=float, default=0.35, help="교통약자 모델 confidence 임계값 (기본 0.35)")
    p.add_argument("--person-conf", type=float, default=0.4, help="사람 모델 confidence 임계값 (기본 0.4)")
    p.add_argument("--max-frames", type=int, default=300, help="최대 처리 프레임 수 (기본 300)")
    p.add_argument("--imgsz", type=int, default=416, help="추론 이미지 크기 (기본 416)")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 모델 로딩
    mob_model = YOLO(args.model)
    person_model = YOLO(args.person_model) if args.person_model else None

    if person_model:
        print(f"[듀얼 모드] 사람 모델: {args.person_model}")
        print(f"            교통약자 모델: {args.model}")
    else:
        print(f"[단일 모드] 교통약자 모델: {args.model}")

    cap = cv2.VideoCapture(args.video)
    if not cap.isOpened():
        print(f"오류: 영상을 열 수 없음 — {args.video}", file=sys.stderr)
        sys.exit(1)

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps_v = cap.get(cv2.CAP_PROP_FPS) or 25
    is_live = total <= 0  # RTSP 등 스트림은 frame count 음수/0
    limit = args.max_frames if is_live else min(total, args.max_frames)
    src_info = "스트림(라이브)" if is_live else f"{total}프레임"
    print(f"영상: {src_info}, {fps_v:.1f}fps → 최대 {args.max_frames}프레임 처리\n")

    saved = 0
    frame_idx = 0
    cumulative_heat: np.ndarray | None = None
    mid_bg_frame: np.ndarray | None = None

    while frame_idx < limit:
        ret, frame = cap.read()
        if not ret:
            break
        frame_idx += 1

        all_detections: list = []

        # ── 교통약자 추론 ──────────────────────────────────────
        mob_results = mob_model.predict(frame, conf=args.conf,
                                        imgsz=args.imgsz, verbose=False)
        fh, fw = frame.shape[:2]
        frame_area = fw * fh
        mob_dets = []
        for box in mob_results[0].boxes.data.tolist():
            x1, y1, x2, y2, conf, cls_id = box
            # 면적 필터: 프레임의 20% 초과 bbox는 오탐으로 제거
            if (x2 - x1) * (y2 - y1) > frame_area * 0.20:
                print(f"  [skip] bbox 과대 {int((x2-x1)*(y2-y1))}/{frame_area} "
                      f"({(x2-x1)*(y2-y1)/frame_area:.1%}) cls={int(cls_id)} conf={conf:.2f}")
                continue
            mob_dets.append((int(x1), int(y1), int(x2), int(y2), conf, cls_id))
        all_detections.extend(mob_dets)

        # ── 사람 추론 (듀얼 모드) ─────────────────────────────
        person_dets = []
        if person_model is not None:
            p_results = person_model.predict(frame, conf=args.person_conf,
                                             imgsz=args.imgsz, verbose=False)
            for box in p_results[0].boxes.data.tolist():
                x1, y1, x2, y2, conf, cls_id = box
                if int(cls_id) != 0:   # person 클래스만
                    continue
                person_dets.append((int(x1), int(y1), int(x2), int(y2), conf, cls_id))
            all_detections.extend(person_dets)

        if not all_detections:
            continue

        # 히트맵 배경용 중간 프레임 보관 (첫 감지 프레임)
        if mid_bg_frame is None:
            mid_bg_frame = frame.copy()

        # ── 그리기 ────────────────────────────────────────────
        annotated = frame.copy()

        # 사람 박스 먼저 (아래 레이어)
        if person_dets:
            annotated = draw_boxes(annotated, person_dets,
                                   class_kr={0: "person"},
                                   class_clr={0: COLOR_PERSON})

        # 교통약자 박스 (위 레이어)
        if mob_dets:
            annotated = draw_boxes(annotated, mob_dets,
                                   class_kr=MOB_CLASS_KR,
                                   class_clr=MOB_CLASS_CLR)

        # 프레임 정보 오버레이
        ts = frame_idx / fps_v
        mode_tag = "[듀얼]" if person_model else "[단일]"
        info = f"{mode_tag} Frame {frame_idx:04d}  {ts:.1f}s"
        annotated = put_kr_text(annotated, info, (10, 6),
                                font_size=20, color_bgr=(0, 255, 255))

        # ── 누적 히트맵 (교통약자만) ──────────────────────────
        h, w = frame.shape[:2]
        if cumulative_heat is None:
            cumulative_heat = np.zeros((h, w), dtype=np.float32)
        accumulate_heat(cumulative_heat, mob_dets)

        # ── 저장 ──────────────────────────────────────────────
        out_path = out_dir / f"debug_{frame_idx:04d}.jpg"
        cv2.imwrite(str(out_path), annotated)
        saved += 1

        mob_names  = [MOB_CLASS_KR.get(int(d[5]), "?") for d in mob_dets]
        p_count    = len(person_dets)
        p_info     = f" | person×{p_count}" if person_model else ""
        print(f"  [{frame_idx:4d}] {mob_names}{p_info} → {out_path.name}")

    cap.release()

    # ── 누적 히트맵 저장 ──────────────────────────────────────
    if cumulative_heat is not None and cumulative_heat.max() > 0:
        hm_path = out_dir / "heatmap_cumulative.jpg"
        save_cumulative_heatmap(cumulative_heat, mid_bg_frame, hm_path)

    print(f"\n완료: {saved}개 프레임 저장 → {out_dir}")


if __name__ == "__main__":
    main()
