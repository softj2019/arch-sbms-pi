import os
import cv2
import base64
import websockets
import json
import asyncio
import urllib.parse
import re
import socket
import sys
from dotenv import load_dotenv

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from core.websocket_endpoint import select_primary_websocket_url, websocket_connection

load_dotenv()
hostname = socket.gethostname()
match = re.search(r'gunpo-(\d+)', hostname)
if match:
    extracted_number = match.group(1)  # 숫자 부분만 추출
else:
    # 호스트네임이 올바르지 않으면 환경변수 TERMINAL_ID 사용
    extracted_number = os.getenv('TERMINAL_ID')  # 기본값 설정

TERMINAL_ID = extracted_number

IP_OPENCV = os.getenv('IP_OPENCV')
USERNAME_OPENCV = os.getenv('USERNAME_OPENCV')
PASSWORD_OPENCV = os.getenv('PASSWORD_OPENCV')
CAMERA_TYPE = os.getenv('CAMERA_TYPE', 'ip').lower()
STATION_TYPE = os.getenv('STATION_TYPE', 'standard').lower()

WEBSOCKET_URL = select_primary_websocket_url(extracted_number)

# STATION_TYPE=smartpole 또는 CAMERA_TYPE=usb 이면 mediamtx RTSP 사용
if STATION_TYPE == 'smartpole' or CAMERA_TYPE == 'usb':
    RTSP_URL = os.getenv('RTSP_STREAM1', 'rtsp://localhost:8554/cam')
else:
    encoded_username = urllib.parse.quote(USERNAME_OPENCV or '', safe='')
    encoded_password = urllib.parse.quote(PASSWORD_OPENCV or '', safe='')
    RTSP_URL = f"rtsp://{encoded_username}:{encoded_password}@{IP_OPENCV}:554/stream2"


async def encode_frame(frame):
    """프레임 크기를 더 축소하고 Base64로 인코딩"""
    frame_resized = cv2.resize(frame, (480, 270))  # 해상도 축소
    _, buffer = cv2.imencode(".jpg", frame_resized, [cv2.IMWRITE_JPEG_QUALITY, 15])  # 압축률 증가
    return base64.b64encode(buffer).decode("utf-8")


def create_stomp_send_frame(destination, message):
    """STOMP SEND 프레임 생성"""
    frame = f"SEND\ndestination:{destination}\ncontent-length:{len(message)}\n\n{message}\x00"
    return frame


async def send_large_message(websocket, destination, message, chunk_size=50000):
    """큰 메시지를 여러 개의 작은 메시지로 분할하여 전송"""
    for i in range(0, len(message), chunk_size):
        chunk = message[i:i + chunk_size]
        send_frame = create_stomp_send_frame(destination=destination, message=chunk)
        await websocket.send(send_frame)


async def send_frames():
    """RTSP 영상을 WebSocket을 통해 전송"""
    cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 480)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 280)

    async with websocket_connection(
        primary_url=WEBSOCKET_URL,
        log_context="cv_req",
        max_size=2 ** 20,
    ) as websocket:  # 1MB 제한
        while cap.isOpened():
            cap.grab()  # 🔥 이전 프레임을 버리고 최신 프레임 유지
            ret, frame = cap.read()
            if not ret:
                break

            encoded_frame = await encode_frame(frame)
            message = json.dumps({"terminalId": TERMINAL_ID, "image": encoded_frame})

            await send_large_message(websocket, destination="/api/cv/stream", message=message)
            await asyncio.sleep(0.05)  # 20 FPS 제한

    cap.release()


if __name__ == "__main__":
    asyncio.run(send_frames())
