import os
import cv2
import logging
import requests
import time
import urllib.parse
import numpy as np
import torch
from dotenv import load_dotenv, dotenv_values
from ultralytics import YOLO
import asyncio
import websockets
import json
from datetime import datetime
import sys
import atexit
import signal
from functools import partial
import re
import socket
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from websocket_endpoint import select_primary_websocket_url, websocket_connection

# ──────────────────────────────────────────────────────────────
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger()

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))  # 상위 디렉토리로 이동
custom_env_path = os.path.join(project_root, ".env_custom")
custom_env = dotenv_values(custom_env_path)
for key, value in custom_env.items():
    os.environ[key] = value

SERVER_API_URL = os.getenv('SERVER_API_URL')
API_URL = os.getenv('API_URL')
USERNAME_OPENCV = os.getenv('USERNAME_OPENCV')
PASSWORD_OPENCV = os.getenv('PASSWORD_OPENCV')
camera_ip = os.getenv('IP_OPENCV')
hostname = socket.gethostname()
match = re.search(r'gunpo-(\d+)', hostname)
TERMINAL_ID = match.group(1) if match else os.getenv('TERMINAL_ID')
STOMP_URL = select_primary_websocket_url(TERMINAL_ID)

server_url = f"{API_URL}/update_count"
encoded_password = urllib.parse.quote(PASSWORD_OPENCV)
rtsp_url = f"rtsp://{USERNAME_OPENCV}:{encoded_password}@{camera_ip}/stream1"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(SCRIPT_DIR, "yolov8m.pt")
if not os.path.exists(MODEL_PATH):
    raise FileNotFoundError(f"YOLO 모델 파일이 없습니다: {MODEL_PATH}")

# ──────────────────────────────────────────────────────────────
device = "cuda" if torch.cuda.is_available() else "cpu"
logger.info(f"Using device: {device}")
model = YOLO(MODEL_PATH).to(device)

cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;udp"

DATA_DIR = "D:\\download\\data" if os.name == "nt" else "/home/admin/data"
os.makedirs(DATA_DIR, exist_ok=True)
if os.name != "nt":
    os.chmod(DATA_DIR, 0o755)


STAT_FILE_PATH = os.path.join(DATA_DIR, "stat_data.json")
def save_stat_count(stat_people_count):
    try:
        with open(STAT_FILE_PATH, "w") as file:
            json.dump({"stat_people_count": stat_people_count}, file)
    except Exception as e:
        logger.error(f"stat_people_count 저장 오류: {e}")

def load_stat_count():
    if os.path.exists(STAT_FILE_PATH):
        try:
            with open(STAT_FILE_PATH, "r") as file:
                data = json.load(file)
                return data.get("stat_people_count", 0)
        except Exception as e:
            logger.error(f"stat_people_count 로드 오류: {e}")
    return 0


IS_WINDOWS = os.name == "nt"


def handle_exit(sig=None, frame=None):
    logger.info("🚪 종료 시그널 수신됨. stat_people_count 저장 중...")
    save_stat_count(stat_people_count)
    sys.exit(0)

signal.signal(signal.SIGINT, handle_exit)

if hasattr(signal, 'SIGTERM'):
    signal.signal(signal.SIGTERM, handle_exit)

atexit.register(handle_exit)

def reconnect_stream():
    global cap
    for _ in range(5):
        cap.release()
        time.sleep(2)
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if cap.isOpened():
            return
    logger.error("RTSP 스트림 재연결 실패")
    sys.exit(1)

if not cap.isOpened():
    reconnect_stream()

# 이미지 업로드 함수
def upload_image(file_path, file_name):
    try:
        upload_url = f"{SERVER_API_URL}/api/upload/image"
        files = {"file": open(file_path, "rb")}
        data = {"file_name": file_name}
        response = requests.post(upload_url, files=files, data=data)
        logger.info(f"Upload Response: {response.status_code} - {response.text}")
        return response.status_code == 200
    except Exception as e:
        logger.error(f"이미지 업로드 실패: {e}")
        return False

# STOMP 메시지 전송 함수
async def send_stomp_message(destination, message):
    try:
        async with websocket_connection(primary_url=STOMP_URL, log_context="cv_yolo") as ws:
            await ws.send("CONNECT\naccept-version:1.1,1.2\nhost:localhost\n\n\x00")
            frame = f"SEND\ndestination:{destination}\n\n{json.dumps(message)}\x00"
            await ws.send(frame)
    except Exception as e:
        logger.error(f"STOMP 전송 오류: {e}")

# ──────────────────────────────────────────────────────────────
fps_limit = 5
frame_interval = int(30 / fps_limit)
prev_time = 0
frame_count = 0
previous_count = 0
stat_people_count = load_stat_count()
last_reset_date = datetime.now().date()
last_detected_frame = None
last_detected_time = None
# ──────────────────────────────────────────────────────────────
while True:
    ret, frame = cap.read()
    if not ret:
        time.sleep(5)
        reconnect_stream()
        continue

    frame_count += 1
    if frame_count % frame_interval != 0:
        continue

    frame_resized = cv2.resize(frame, (640, 480))
    if time.time() - prev_time < 1 / fps_limit:
        continue
    prev_time = time.time()

    results = model.predict(frame_resized, conf=0.4)
    people_boxes = [obj for obj in results[0].boxes.data if int(obj[5]) == 0]
    people_count = len(people_boxes)

    if people_count > 0:
        # 이미지 저장 디렉토리 설정
        debug_img_dir = "/home/admin/data/debug_images" if os.name != "nt" else "d:/download/debug_images"
        os.makedirs(debug_img_dir, exist_ok=True)
        now = datetime.now()
        file_name = f"frame_{TERMINAL_ID}_{now.strftime('%Y%m%d%H%M%S')}.jpg"
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        frame_path = os.path.join(debug_img_dir, file_name)
        cv2.imwrite(frame_path, frame_resized)
        try:
            response = requests.post(server_url, json={"count": people_count})
            if response.status_code == 200:
                logger.info(f"통합제어보드로 인원 수 전송 성공: {people_count}")
            else:
                logger.warning(f"⚠통합제어보드 전송 실패: {response.status_code} - {response.text}")
        except Exception as e:
            logger.error(f"통합제어보드 전송 오류: {e}")

        upload_image(frame_path, file_name)

        stomp_payload = {
            "terminal_id": TERMINAL_ID,
            "people_count": people_count,
            "stat_people_count": stat_people_count,
            "timestamp": timestamp,
            "file_name": file_name
        }
        asyncio.run(send_stomp_message("/api/iot/hid", stomp_payload))

    else:
        previous_count = people_count
