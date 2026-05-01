"""
Open Images V7에서 교통약자 감지용 데이터셋 다운로드 및 YOLO 포맷 변환
클래스: Wheelchair, Crutch, Baby carriage
"""
import fiftyone as fo
import fiftyone.zoo as foz
import os
import shutil
import yaml

CLASSES = ["Wheelchair", "Crutch", "Baby carriage"]
BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "datasets", "mobility_aids")

def download_and_export():
    print(f"=== Open Images V7 다운로드 시작 ===")
    print(f"클래스: {CLASSES}")
    print(f"저장 경로: {BASE_DIR}")

    for split in ["train", "validation"]:
        print(f"\n--- {split} set 다운로드 중 ---")
        ds = foz.load_zoo_dataset(
            "open-images-v7",
            split=split,
            classes=CLASSES,
            label_types=["detections"],
            only_matching=True,
        )
        print(f"{split}: {len(ds)} samples 다운로드 완료")

        export_dir = os.path.join(BASE_DIR, split)
        ds.export(
            export_dir=export_dir,
            dataset_type=fo.types.YOLOv5Dataset,
            label_field="ground_truth",
            classes=CLASSES,
        )
        print(f"{split}: YOLO 포맷 export 완료 → {export_dir}")
        fo.delete_dataset(ds.name)

    # dataset.yaml 생성
    dataset_yaml = {
        "path": BASE_DIR.replace("\\", "/"),
        "train": "train/images",
        "val": "validation/images",
        "nc": len(CLASSES),
        "names": {i: name for i, name in enumerate(CLASSES)},
    }

    yaml_path = os.path.join(BASE_DIR, "dataset.yaml")
    with open(yaml_path, "w") as f:
        yaml.dump(dataset_yaml, f, default_flow_style=False, allow_unicode=True)

    print(f"\n=== 완료 ===")
    print(f"dataset.yaml: {yaml_path}")

    # 통계 출력
    for split in ["train", "validation"]:
        img_dir = os.path.join(BASE_DIR, split, "images")
        if os.path.exists(img_dir):
            count = len([f for f in os.listdir(img_dir) if f.endswith(('.jpg', '.png', '.jpeg'))])
            print(f"  {split}: {count} images")

if __name__ == "__main__":
    download_and_export()
