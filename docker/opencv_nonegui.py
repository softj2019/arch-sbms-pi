import os
import cv2
import logging
import requests
import time
import urllib.parse
from dotenv import load_dotenv

load_dotenv()

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger()
API_URL = os.getenv('API_URL')
USERNAME_OPENCV = os.getenv('USERNAME_OPENCV')
PASSWORD_OPENCV = os.getenv('PASSWORD_OPENCV')
# RTSP 정보
username = USERNAME_OPENCV
password = PASSWORD_OPENCV
camera_ip = os.getenv('IP_OPENCV')
encoded_password = urllib.parse.quote(password)
rtsp_url = f"rtsp://{username}:{encoded_password}@{camera_ip}/stream1"

# RTSP 스트림 연결
cap = cv2.VideoCapture(rtsp_url)

if not cap.isOpened():
    logger.error("🚨 RTSP 스트림에 연결할 수 없습니다. 10초 후 재시도...")
    time.sleep(10)  # 일정 시간 대기 후 재시도
    exit()

logger.info("✅ RTSP 스트림에 성공적으로 연결되었습니다.")

# HOGDescriptor를 이용한 사람 검출기 초기화
hog = cv2.HOGDescriptor()
hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

# Flask 서버 URL
server_url = f"{API_URL}/update_count"

# 기존 인원 수 저장 변수 (초기값 -1)
previous_count = -1

while True:
    ret, frame = cap.read()
    if not ret:
        logger.error("🚨 RTSP 프레임 읽기 실패. 5초 후 재시도...")
        time.sleep(5)
        continue  # 오류 발생 시 루프 재시작

    # 프레임 크기 조정
    frame = cv2.resize(frame, (640, 480))

    # 사람 검출
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    boxes, weights = hog.detectMultiScale(
        gray, winStride=(8, 8), padding=(16, 16), scale=1.05
    )

    # 현재 검출된 사람 수
    people_count = len(boxes)

    # 인원 수 변동이 있는 경우에만 서버로 전송
    if people_count != previous_count:
        try:
            response = requests.post(server_url, json={"count": people_count})
            if response.status_code == 200:
                logger.info(f"✅ 변동 감지! 서버로 전송: {people_count}명")
                previous_count = people_count  # 새로운 인원 수 저장
            else:
                logger.error(f"🚨 서버 전송 실패: {response.text}")
        except Exception as e:
            logger.error(f"🚨 서버 전송 오류: {e}")

    # CPU 부하 방지 (1초 대기)
    time.sleep(1)

# 리소스 해제
cap.release()
logger.info("🔄 RTSP 스트림 종료, 프로그램 종료")
