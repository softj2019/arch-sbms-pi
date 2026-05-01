"""
YOLO11n 교통약자 감지 로컬 파인튜닝
GPU: RTX PRO 6000 (98GB) + RTX 5090 (32GB)
클래스: Wheelchair, Crutch, Baby carriage
"""
import os
import torch
from ultralytics import YOLO

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_YAML = os.path.join(PROJECT_ROOT, "datasets", "mobility_aids", "dataset.yaml")
RUNS_DIR = os.path.join(PROJECT_ROOT, "runs")

def main():
    # GPU 확인
    print(f"CUDA available: {torch.cuda.is_available()}")
    print(f"GPU count: {torch.cuda.device_count()}")
    for i in range(torch.cuda.device_count()):
        name = torch.cuda.get_device_name(i)
        mem = torch.cuda.get_device_properties(i).total_memory / 1024**3
        print(f"  GPU {i}: {name} ({mem:.0f} GB)")

    # 데이터셋 확인
    if not os.path.exists(DATASET_YAML):
        print(f"\n[ERROR] dataset.yaml not found: {DATASET_YAML}")
        print("먼저 python scripts/download_dataset.py 를 실행하세요.")
        return

    print(f"\nDataset: {DATASET_YAML}")

    # YOLO11n 로드 (COCO pretrained)
    model = YOLO("yolo11n.pt")

    # 학습 시작 - RTX PRO 6000 (GPU 0) 사용
    results = model.train(
        data=DATASET_YAML,
        epochs=100,
        batch=-1,              # auto batch size (VRAM 맞춤 자동 설정)
        imgsz=640,
        device=0,              # RTX PRO 6000
        patience=20,           # early stopping
        workers=8,
        project=RUNS_DIR,
        name="mobility_yolo11n",
        exist_ok=True,
        # 학습 최적화
        lr0=0.01,
        lrf=0.01,
        warmup_epochs=3,
        augment=True,
        mosaic=1.0,
        mixup=0.1,
        copy_paste=0.1,
        amp=True,              # mixed precision
    )

    print(f"\n=== 학습 완료 ===")
    print(f"Best model: {results.save_dir}/weights/best.pt")

    # 검증
    best_path = os.path.join(results.save_dir, "weights", "best.pt")
    model_best = YOLO(best_path)
    metrics = model_best.val(data=DATASET_YAML)
    print(f"mAP50: {metrics.box.map50:.3f}")
    print(f"mAP50-95: {metrics.box.map:.3f}")

    # Pi용 OpenVINO INT8 export
    print("\n=== OpenVINO INT8 export (Pi 5 배포용) ===")
    model_best.export(format="openvino", imgsz=640, int8=True)
    print("Export 완료!")

    # ONNX export (범용)
    print("\n=== ONNX export ===")
    model_best.export(format="onnx", imgsz=640)
    print("Export 완료!")

if __name__ == "__main__":
    main()
