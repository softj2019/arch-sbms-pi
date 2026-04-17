import os
import time
import cv2
import torch
from datetime import datetime
from dotenv import load_dotenv, dotenv_values
from ultralytics import YOLO
import logging
import re
import socket
import urllib.request
import requests
import json
import urllib.parse
import atexit
import signal
import sys
import threading
import websockets
import asyncio
import subprocess
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from websocket_endpoint import select_primary_websocket_url, websocket_connection

# 기본 설정
load_dotenv()
capture_path = "/home/admin/data/capture.jpg"
debug_dir = "/home/admin/data/debug_images"
os.makedirs(debug_dir, exist_ok=True)


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("PeopleDetector")

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
custom_env_path = os.path.join(project_root, ".env_custom")
custom_env = dotenv_values(custom_env_path)
for key, value in custom_env.items():
    os.environ[key] = value
SERVER_API_URL = os.getenv('SERVER_API_URL')
USERNAME_OPENCV = os.getenv('USERNAME_OPENCV')
PASSWORD_OPENCV = os.getenv('PASSWORD_OPENCV')
camera_ip = os.getenv('IP_OPENCV')
hostname = socket.gethostname()
match = re.search(r'gunpo-(\d+)', hostname)
TERMINAL_ID = match.group(1) if match else os.getenv('TERMINAL_ID')
STOMP_URL = select_primary_websocket_url(TERMINAL_ID)

SCRIPT_DIR = "d:/download/yolo" if os.name == "nt" else "/home/admin/data"
MODEL_PATH = os.path.join(SCRIPT_DIR, "yolov8n.pt")  # YOLOv8n 경량 모델로 교체
if not os.path.exists(MODEL_PATH):
    logger.info("YOLO 모델 다운로드 시작...")
    url = "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt"
    os.makedirs(SCRIPT_DIR, exist_ok=True)
    urllib.request.urlretrieve(url, MODEL_PATH)
    logger.info("YOLO 모델 다운로드 완료")

device = "cuda" if torch.cuda.is_available() else "cpu"
logger.info(f"Using device: {device}")
model = YOLO(MODEL_PATH).to(device)

DATA_DIR = "D:\\download\\data" if os.name == "nt" else "/home/admin/data"
os.makedirs(DATA_DIR, exist_ok=True)
if os.name != "nt":
    os.chmod(DATA_DIR, 0o755)


API_URL = os.getenv('API_URL')
server_url = f"{API_URL}/update_count"
encoded_password = urllib.parse.quote(PASSWORD_OPENCV)
rtsp_url = f"rtsp://{USERNAME_OPENCV}:{encoded_password}@{camera_ip}/stream1"

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


def upload_image(file_path, file_name):
    file_size = os.path.getsize(file_path)
    logger.info(f"📦 업로드 파일 크기: {file_size / 1024:.2f} KB")
    try:
        upload_url = f"{SERVER_API_URL}/api/upload/image"
        files = {"file": open(file_path, "rb")}
        data = {"file_name": file_name}
        response = requests.post(upload_url, files=files, data=data)
        logger.info(f"✅ 이미지 업로드 성공: {response.status_code}")
        return response.status_code == 200
    except Exception as e:
        logger.error(f"❌ 이미지 업로드 실패: {e}")
        return False

stat_people_count = load_stat_count()
last_reset_date = datetime.now().date()
previous_count = 0

# ── RCWL-0516 레이더 융합 ─────────────────────────────────────
RADAR_PIN = int(os.getenv("RADAR_GPIO_PIN", "3"))
RADAR_HOLDTIME = float(os.getenv("RADAR_HOLDTIME", "3.0"))  # 센서 홀드타임(초)
RADAR_FALLBACK_INTERVAL = float(os.getenv("RADAR_FALLBACK_INTERVAL", "15.0"))  # 레이더 없을 때 폴링 주기

_radar_event = threading.Event()

def _radar_callback(channel):
    logger.debug(f"RCWL-0516 감지 (GPIO{channel})")
    _radar_event.set()

try:
    import RPi.GPIO as GPIO
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(RADAR_PIN, GPIO.IN)
    GPIO.add_event_detect(RADAR_PIN, GPIO.RISING, callback=_radar_callback, bouncetime=300)
    RADAR_ENABLED = True
    logger.info(f"✅ RCWL-0516 레이더 활성화 (GPIO{RADAR_PIN})")
except Exception as e:
    RADAR_ENABLED = False
    logger.warning(f"⚠️ RCWL-0516 초기화 실패 - 폴링 모드로 동작: {e}")

def handle_exit(sig=None, frame=None):
    if RADAR_ENABLED:
        try:
            import RPi.GPIO as GPIO
            GPIO.cleanup()
        except Exception:
            pass
    save_stat_count(stat_people_count)
    sys.exit(0)

signal.signal(signal.SIGINT, handle_exit)
if hasattr(signal, 'SIGTERM'):
    signal.signal(signal.SIGTERM, handle_exit)
atexit.register(lambda: save_stat_count(stat_people_count))

DEBUG_IMG_DIR = "/home/admin/data/debug_images" if os.name != "nt" else "d:/download/debug_images"
os.makedirs(DEBUG_IMG_DIR, exist_ok=True)

async def send_stomp_message(destination, message, max_retries=3):
    for attempt in range(1, max_retries + 1):
        try:
            async with websocket_connection(primary_url=STOMP_URL, log_context="cv_ffmpeg") as ws:
                await ws.send("CONNECT\naccept-version:1.1,1.2\nhost:localhost\n\n\x00")
                frame = f"SEND\ndestination:{destination}\n\n{json.dumps(message)}\x00"
                await ws.send(frame)
                logger.info(f"✅ STOMP 전송 성공 (시도 {attempt})")
                return
        except Exception as e:
            logger.warning(f"⚠️ STOMP 전송 실패 (시도 {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                await asyncio.sleep(2)
            else:
                logger.error("❌ STOMP 전송 최종 실패")

while True:
    # 레이더 감지 대기 (타임아웃 시 폴링 폴백)
    if RADAR_ENABLED:
        triggered = _radar_event.wait(timeout=RADAR_FALLBACK_INTERVAL)
        _radar_event.clear()
        if triggered:
            logger.info("🎯 레이더 트리거 → 카메라 추론 시작")
        else:
            logger.debug("⏱ 레이더 무신호 - 폴링 폴백 추론")
    try:
        # 1. 이미지 캡처 (1프레임만 저장)
        ffmpeg_cmd = [
            "ffmpeg",
            "-loglevel", "quiet",
            "-rtsp_transport", "udp",
            "-i", rtsp_url,
            "-vframes", "1",
            "-q:v", "2",
            "-update", "1",
            "-y", capture_path
        ]

        subprocess.run(ffmpeg_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        if not os.path.exists(capture_path):
            logger.warning("⚠️ 캡처 실패 - 파일 없음")
            time.sleep(3)
            continue

        # 2. 이미지 로딩 및 YOLO 추론
        image = cv2.imread(capture_path)
        if image is None:
            logger.warning("⚠️ 이미지 로딩 실패")
            time.sleep(3)
            continue

        results = model.predict(image, conf=0.4)
        people = []
        for box in results[0].boxes.data:
            x1, y1, x2, y2, conf, cls_id = box.tolist()
            x1, y1, x2, y2 = map(int, (x1, y1, x2, y2))
            class_id = int(cls_id)

            if class_id == 0:  # only person
                w, h = x2 - x1, y2 - y1
                if w < 10 or h < 20:
                    continue
                aspect_ratio = h / w if w != 0 else 0
                if aspect_ratio < 0.2 or aspect_ratio > 4.0:
                    continue
                people.append((x1, y1, x2, y2))
            label = f"{class_id} ({conf:.2f})"
            cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(image, label, (x1, y1 - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        logger.info(f"👥 감지된 인원 수: {len(people)}")

        if len(people) > previous_count:
            stat_people_count += len(people) - previous_count
        elif len(people) == 0:
            previous_count = 0
        previous_count = len(people)


        if people:
            for box in people:
                x1, y1, x2, y2 = map(int, box[:4])
                cv2.rectangle(image, (x1, y1), (x2, y2), (0, 255, 0), 2)

            # now = datetime.now()
            file_name = f"Debug off"
            # file_name = f"frame_{TERMINAL_ID}_{now.strftime('%Y%m%d%H%M%S')}.jpg"
            # debug_img_path = os.path.join(debug_dir, file_name)
            # cv2.imwrite(debug_img_path, image, [cv2.IMWRITE_JPEG_QUALITY, 70])
            # logger.info(f"🖼️ 디버깅 이미지 저장됨: {debug_img_path}")

            try:
                response = requests.post(server_url, json={"count": len(people)})
                if response.status_code == 200:
                    logger.info(f"통합제어보드로 인원 수 전송 성공: {len(people)}")
                else:
                    logger.warning(f"⚠통합제어보드 전송 실패: {response.status_code} - {response.text}")
            except Exception as e:
                logger.error(f"통합제어보드 전송 오류: {e}")


            # upload_image(debug_img_path, file_name)

            stomp_payload = {
                "terminal_id": TERMINAL_ID,
                "people_count": len(people),
                "stat_people_count": stat_people_count,
                 "file_name": file_name
            }
            asyncio.run(send_stomp_message("/api/iot/hid", stomp_payload))

        else:
            logger.info("👤 사람 없음 - 이미지 저장 생략")

    except Exception as e:
        logger.exception(f"❌ 오류 발생: {e}")

    if not RADAR_ENABLED:
        time.sleep(3)  # 레이더 없으면 기존 폴링 유지
    else:
        time.sleep(RADAR_HOLDTIME)  # 레이더 홀드타임 동안 대기 (중복 트리거 방지)
