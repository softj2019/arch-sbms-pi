"""
트리거 기반 파인튜닝 데이터 수집

조건: person + wheelchair 동시 감지 시 프레임 저장
출력: finetune_set_01.zip ~ finetune_set_10.zip (각 100장 + YOLO 라벨)
"""
import cv2
import sys
import time
import zipfile
import shutil
import argparse
from pathlib import Path
from ultralytics import YOLO

# ── 기본값 ────────────────────────────────────────────────────
RTSP_URL        = "rtsp://localhost:8554/cam"
MOB_MODEL_PATH  = "/home/admin/data/mobility_yolo11n_best.pt"
PERS_MODEL_PATH = "/home/admin/data/yolo11n.pt"
OUT_BASE        = "/home/admin/data/finetune_dataset"
FRAMES_PER_SET  = 100
TOTAL_SETS      = 10
MOB_CONF        = 0.30   # 수집용은 낮게
PERSON_CONF     = 0.30   # bicycle(cls=1)로 감지되는 경우 포함
IMGSZ           = 416
AREA_MAX_RATIO  = 0.20   # 오탐 면적 필터
SKIP_FRAMES     = 5      # 중복 방지: N프레임마다 1장


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="파인튜닝 데이터 수집 (person+wheelchair 트리거)")
    p.add_argument("--rtsp",        default=RTSP_URL)
    p.add_argument("--mob-model",   default=MOB_MODEL_PATH)
    p.add_argument("--pers-model",  default=PERS_MODEL_PATH)
    p.add_argument("--out",         default=OUT_BASE)
    p.add_argument("--frames",      type=int, default=FRAMES_PER_SET)
    p.add_argument("--sets",        type=int, default=TOTAL_SETS)
    p.add_argument("--mob-conf",    type=float, default=MOB_CONF)
    p.add_argument("--pers-conf",   type=float, default=PERSON_CONF)
    p.add_argument("--skip",        type=int, default=SKIP_FRAMES, help="N프레임 간격으로 저장")
    return p.parse_args()


def make_set_dirs(base: Path, set_idx: int):
    d = base / f"set_{set_idx:02d}_tmp"
    (d / "images").mkdir(parents=True, exist_ok=True)
    (d / "labels").mkdir(parents=True, exist_ok=True)
    return d


def zip_set(tmp_dir: Path, out_base: Path, set_idx: int) -> Path:
    zip_path = out_base / f"finetune_set_{set_idx:02d}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in tmp_dir.rglob("*"):
            if f.is_file():
                zf.write(f, f.relative_to(tmp_dir))
    return zip_path


def write_yaml(tmp_dir: Path) -> None:
    (tmp_dir / "data.yaml").write_text(
        f"path: {tmp_dir}\n"
        "train: images\n"
        "val: images\n"
        "nc: 2\n"
        "names: ['Wheelchair', 'Crutch']\n"
    )


MOB_CLASS_KR = {0: "휠체어", 1: "목발"}


def main() -> None:
    args = parse_args()
    out_base = Path(args.out)
    out_base.mkdir(parents=True, exist_ok=True)

    print(f"모델 로딩 중...")
    mob_model  = YOLO(args.mob_model)
    pers_model = YOLO(args.pers_model)
    print(f"  교통약자: {args.mob_model}")
    print(f"  사람:     {args.pers_model}")

    cap = cv2.VideoCapture(args.rtsp, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if not cap.isOpened():
        print(f"RTSP 연결 실패: {args.rtsp}", file=sys.stderr)
        sys.exit(1)
    print(f"RTSP 연결: {args.rtsp}\n")
    print(f"수집 목표: {args.sets}세트 × {args.frames}장 = {args.sets * args.frames}장")
    print(f"트리거: person + wheelchair 동시 감지")
    print(f"출력: {out_base}\n")

    set_idx     = 1
    saved       = 0
    raw_frame_n = 0
    tmp_dir     = make_set_dirs(out_base, set_idx)

    while set_idx <= args.sets:
        # 버퍼 플러시 (최신 프레임)
        for _ in range(3):
            cap.grab()
        ret, frame = cap.retrieve()
        if not ret or frame is None:
            time.sleep(0.2)
            continue

        raw_frame_n += 1

        # ── 교통약자 추론 ──────────────────────────────────────
        fh, fw = frame.shape[:2]
        frame_area = fw * fh
        mob_res  = mob_model.predict(frame, conf=args.mob_conf,
                                     imgsz=IMGSZ, verbose=False)
        mob_dets = []
        for box in mob_res[0].boxes.data.tolist():
            x1, y1, x2, y2, conf, cls_id = box
            if (x2 - x1) * (y2 - y1) > frame_area * AREA_MAX_RATIO:
                continue  # 오탐 면적 필터
            mob_dets.append((int(x1), int(y1), int(x2), int(y2), conf, int(cls_id)))

        if not mob_dets:
            continue

        # ── 사람 추론 ─────────────────────────────────────────
        p_res   = pers_model.predict(frame, conf=args.pers_conf,
                                     imgsz=IMGSZ, verbose=False)
        # person(0) / bicycle(1) / motorcycle(3) — 휠체어 탑승자가 bicycle로 감지되는 경우 포함
        _PERSON_LIKE = {0, 1, 3}
        p_dets  = [
            (int(x1), int(y1), int(x2), int(y2), conf, int(cls_id))
            for x1, y1, x2, y2, conf, cls_id in p_res[0].boxes.data.tolist()
            if int(cls_id) in _PERSON_LIKE
        ]

        if not p_dets:
            continue  # 사람 없으면 스킵

        # ── 중복 방지 (skip 간격) ────────────────────────────
        if raw_frame_n % args.skip != 0:
            continue

        # ── 저장 ──────────────────────────────────────────────
        saved += 1
        stem  = f"set{set_idx:02d}_{saved:04d}"

        cv2.imwrite(str(tmp_dir / "images" / f"{stem}.jpg"), frame)

        with open(tmp_dir / "labels" / f"{stem}.txt", "w") as lf:
            for x1, y1, x2, y2, _, cls_id in mob_dets:
                cx = ((x1 + x2) / 2) / fw
                cy = ((y1 + y2) / 2) / fh
                wn = (x2 - x1) / fw
                hn = (y2 - y1) / fh
                lf.write(f"{cls_id} {cx:.6f} {cy:.6f} {wn:.6f} {hn:.6f}\n")

        mob_names = [MOB_CLASS_KR.get(d[5], "?") for d in mob_dets]
        print(f"  [세트{set_idx:02d} {saved:3d}/{args.frames}] "
              f"{mob_names} | person×{len(p_dets)}")

        # ── 세트 완성 → ZIP ──────────────────────────────────
        if saved >= args.frames:
            write_yaml(tmp_dir)
            zip_path = zip_set(tmp_dir, out_base, set_idx)
            size_kb  = zip_path.stat().st_size // 1024
            print(f"\n{'='*50}")
            print(f" 세트 {set_idx:02d}/{args.sets} 완성 → {zip_path.name} ({size_kb} KB)")
            print(f"{'='*50}\n")
            shutil.rmtree(tmp_dir)

            set_idx += 1
            saved    = 0
            if set_idx <= args.sets:
                tmp_dir = make_set_dirs(out_base, set_idx)
                time.sleep(1)

    cap.release()
    print(f"\n완료: {args.sets}세트 수집 → {out_base}")


if __name__ == "__main__":
    main()
