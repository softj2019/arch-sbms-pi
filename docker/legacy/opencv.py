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
rtsp_url = f"rtsp://{username}:{encoded_password}@{camera_ip}/stream2"

# RTSP 스트림 연결
cap = cv2.VideoCapture(rtsp_url)

if not cap.isOpened():
    logger.error("RTSP 스트림에 연결할 수 없습니다.")
    exit()

logger.info("RTSP 스트림에 성공적으로 연결되었습니다.")

# HOGDescriptor를 이용한 사람 검출기 초기화
hog = cv2.HOGDescriptor()
hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

# Flask 서버 URL
server_url = f"{API_URL}/update_count"

# 마지막 전송 시간 초기화
last_sent_time = time.time()

while True:
    ret, frame = cap.read()
    if not ret:
        logger.error("RTSP 프레임 읽기 실패.")
        break

    # 프레임 크기 조정
    frame = cv2.resize(frame, (640, 480))

    # 사람 검출
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    boxes, weights = hog.detectMultiScale(
        gray, winStride=(8, 8), padding=(16, 16), scale=1.05
    )

    # 검출된 사람 표시
    people_count = len(boxes)
    for (x, y, w, h) in boxes:
        cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

    # 5초 간격으로 서버 전송
    current_time = time.time()
    if current_time - last_sent_time >= 5:
        try:
            response = requests.post(server_url, json={"count": people_count})
            if response.status_code == 200:
                logger.info(f"Count sent successfully: {people_count}")
            else:
                logger.error(f"Failed to send count: {response.text}")
        except Exception as e:
            logger.error(f"Error sending count to server: {e}")
        last_sent_time = current_time  # 마지막 전송 시간 갱신

    # 화면 출력
    cv2.putText(frame, f"People: {people_count}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    cv2.imshow("People Counting", frame)

    # ESC 키로 종료
    if cv2.waitKey(1) & 0xFF == 27:
        break

# 리소스 해제
cap.release()
cv2.destroyAllWindows()
