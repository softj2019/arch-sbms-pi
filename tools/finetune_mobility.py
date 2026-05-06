"""
GPU 파인튜닝 스크립트 (arch-ai / 10.0.0.115)

사용법:
  python tools/finetune_mobility.py \
    --data-dir /data/finetune_dataset \
    --base-model /data/mobility_yolo11n_best.pt \
    --epochs 50 \
    --out /data/finetune_out
"""
import argparse
import shutil
import yaml
import random
from pathlib import Path
from ultralytics import YOLO


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="교통약자 모델 파인튜닝")
    p.add_argument("--data-dir",    required=True,
                   help="수집된 ZIP들을 압축해제한 디렉토리 (또는 이미 통합된 데이터셋 루트)")
    p.add_argument("--base-model",  default="mobility_yolo11n_best.pt",
                   help="파인튜닝 기반 모델 경로")
    p.add_argument("--out",         default="./finetune_out",
                   help="결과 저장 디렉토리")
    p.add_argument("--epochs",      type=int, default=50)
    p.add_argument("--imgsz",       type=int, default=416)
    p.add_argument("--batch",       type=int, default=16)
    p.add_argument("--lr",          type=float, default=0.001)
    p.add_argument("--val-ratio",   type=float, default=0.15,
                   help="검증 세트 비율 (기본 15%)")
    p.add_argument("--device",      default="0", help="GPU 번호 또는 'cpu'")
    return p.parse_args()


def merge_sets(data_dir: Path, out_dir: Path, val_ratio: float) -> Path:
    """여러 세트의 images/labels를 train/val로 병합 → data.yaml 생성"""
    train_img = out_dir / "images" / "train"
    val_img   = out_dir / "images" / "val"
    train_lbl = out_dir / "labels" / "train"
    val_lbl   = out_dir / "labels" / "val"
    for d in [train_img, val_img, train_lbl, val_lbl]:
        d.mkdir(parents=True, exist_ok=True)

    # 모든 이미지 수집
    all_images = sorted(data_dir.rglob("images/*.jpg"))
    if not all_images:
        all_images = sorted(data_dir.rglob("*.jpg"))
    random.shuffle(all_images)

    n_val   = max(1, int(len(all_images) * val_ratio))
    val_set = set(all_images[:n_val])
    train_s = all_images[n_val:]

    def copy_pair(img_path: Path, img_dst: Path, lbl_dst: Path):
        shutil.copy2(img_path, img_dst / img_path.name)
        lbl_src = img_path.parent.parent / "labels" / img_path.with_suffix(".txt").name
        if lbl_src.exists():
            shutil.copy2(lbl_src, lbl_dst / lbl_src.name)

    for img in train_s:
        copy_pair(img, train_img, train_lbl)
    for img in val_set:
        copy_pair(img, val_img, val_lbl)

    print(f"데이터셋 병합: train={len(train_s)}장, val={len(val_set)}장")

    yaml_path = out_dir / "data.yaml"
    yaml_path.write_text(
        f"path: {out_dir}\n"
        "train: images/train\n"
        "val: images/val\n"
        "nc: 2\n"
        "names: ['Wheelchair', 'Crutch']\n"
    )
    return yaml_path


def main() -> None:
    args    = parse_args()
    data_dir = Path(args.data_dir)
    out_dir  = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 데이터셋 병합
    dataset_dir = out_dir / "dataset"
    yaml_path   = merge_sets(data_dir, dataset_dir, args.val_ratio)

    # 파인튜닝
    print(f"\n파인튜닝 시작")
    print(f"  기반 모델: {args.base_model}")
    print(f"  epochs={args.epochs}, imgsz={args.imgsz}, batch={args.batch}, lr={args.lr}")
    print(f"  device={args.device}\n")

    model = YOLO(args.base_model)
    results = model.train(
        data       = str(yaml_path),
        epochs     = args.epochs,
        imgsz      = args.imgsz,
        batch      = args.batch,
        lr0        = args.lr,
        device     = args.device,
        project    = str(out_dir),
        name       = "mobility_ft",
        exist_ok   = True,
        # 파인튜닝 최적화
        freeze     = 10,        # backbone 10레이어 freeze
        patience   = 15,        # early stopping
        save       = True,
        plots      = True,
        augment    = True,
        hsv_h      = 0.015,
        hsv_s      = 0.4,
        hsv_v      = 0.3,
        fliplr     = 0.5,
        degrees    = 5.0,
    )

    best = out_dir / "mobility_ft" / "weights" / "best.pt"
    deploy = out_dir / "mobility_yolo11n_finetuned.pt"
    if best.exists():
        shutil.copy2(best, deploy)
        print(f"\n파인튜닝 완료 → {deploy}")
        print(f"배포: scp {deploy} admin@sola-1:/home/admin/data/mobility_yolo11n_best.pt")
    else:
        print("\n학습 완료 (best.pt 경로 확인 필요)")


if __name__ == "__main__":
    main()
