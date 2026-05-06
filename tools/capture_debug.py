import cv2
import time
import os
from ultralytics import YOLO

RTSP_URL = "rtsp://localhost:8554/cam"
MODEL_PATH = "/home/admin/data/mobility_yolo11n_best.pt"
OUT_DIR = "/home/admin/data/debug_capture"
os.makedirs(OUT_DIR, exist_ok=True)

model = YOLO(MODEL_PATH)
print("모델 로딩 완료:", MODEL_PATH)

cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

if not cap.isOpened():
    print("RTSP 연결 실패")
    exit(1)
print("RTSP 연결 성공")

saved = 0
attempt = 0
CLASS_NAMES = {0: "Wheelchair", 1: "Crutch"}
COLORS = {0: (0, 165, 255), 1: (0, 255, 0)}  # 주황/초록

while saved < 5 and attempt < 60:
    for _ in range(3):
        cap.grab()
    ret, frame = cap.retrieve()
    attempt += 1
    if not ret or frame is None:
        time.sleep(0.5)
        continue

    resized = cv2.resize(frame, (640, 480))

    # conf=0.25 — 낮은 신뢰도까지 전부 시각화
    results = model.predict(resized, conf=0.25, imgsz=640, verbose=False)

    annotated = resized.copy()
    for box in results[0].boxes.data:
        x1, y1, x2, y2, conf, cls_id = box.tolist()
        x1, y1, x2, y2 = int(x1), int(y1), int(x2), int(y2)
        cls_id = int(cls_id)
        name = CLASS_NAMES.get(cls_id, str(cls_id))
        color = COLORS.get(cls_id, (200, 200, 200))
        cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
        label = name + " " + str(round(conf, 2))
        cv2.putText(annotated, label, (x1, max(y1 - 6, 10)),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

    det_count = len(results[0].boxes.data)
    summary = "det=" + str(det_count)
    cv2.putText(annotated, summary, (8, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    fname = OUT_DIR + "/cap_" + str(saved + 1).zfill(2) + ".jpg"
    raw_fname = OUT_DIR + "/raw_" + str(saved + 1).zfill(2) + ".jpg"
    cv2.imwrite(fname, annotated)
    cv2.imwrite(raw_fname, resized)
    print("저장:", fname, "| 감지:", det_count, "개")

    for b in results[0].boxes.data:
        x1, y1, x2, y2, conf, cls_id = b.tolist()
        name = CLASS_NAMES.get(int(cls_id), "?")
        print("  -", name, "conf=" + str(round(conf, 3)),
              "box=[" + str(int(x1)) + "," + str(int(y1)) + "," + str(int(x2)) + "," + str(int(y2)) + "]")

    saved += 1
    time.sleep(1.5)

cap.release()
print("완료:", OUT_DIR, "에", saved * 2, "장 저장")
