import cv2
import logging
import requests
import time

# 로깅 설정
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger()

# 동영상 파일 경로
video_path = "C:/Users/my/Downloads/downloaded_video.mp4"

# VideoCapture 객체 생성
cap = cv2.VideoCapture(video_path)

if not cap.isOpened():
    logger.error("동영상을 열 수 없습니다.")
    exit()

logger.info("동영상 열기 성공")

# 원본 동영상의 FPS 확인
fps = int(cap.get(cv2.CAP_PROP_FPS))
logger.info(f"동영상 FPS: {fps}")

# HOGDescriptor를 이용한 사람 검출기 초기화
hog = cv2.HOGDescriptor()
hog.setSVMDetector(cv2.HOGDescriptor_getDefaultPeopleDetector())

# 초기 ROI 설정
roi_top_left = [100, 100]
roi_bottom_right = [500, 400]
drawing = False  # 드래그 상태

# Flask 서버 URL
server_url = "http://10.0.0.228:5000/update_count"

# 마지막 전송 시간 초기화
last_sent_time = time.time()

# 마우스 콜백 함수 정의
def set_roi(event, x, y, flags, param):
    global roi_top_left, roi_bottom_right, drawing

    if event == cv2.EVENT_LBUTTONDOWN:  # 드래그 시작
        drawing = True
        roi_top_left = [x, y]

    elif event == cv2.EVENT_MOUSEMOVE and drawing:  # 드래그 중
        roi_bottom_right = [x, y]

    elif event == cv2.EVENT_LBUTTONUP:  # 드래그 종료
        drawing = False
        roi_bottom_right = [x, y]
        logger.info(f"새 ROI 설정: {roi_top_left} -> {roi_bottom_right}")

# OpenCV 창에 마우스 콜백 연결
cv2.namedWindow("ROI People Counting")
cv2.setMouseCallback("ROI People Counting", set_roi)

while True:
    ret, frame = cap.read()
    if not ret:
        logger.info("동영상 끝")
        break

    # 프레임 크기 조정
    frame = cv2.resize(frame, (640, 480))

    # ROI 영역 표시
    cv2.rectangle(frame, tuple(roi_top_left), tuple(roi_bottom_right), (255, 0, 0), 2)

    # 사람 검출
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    boxes, weights = hog.detectMultiScale(
        gray, winStride=(8, 8), padding=(16, 16), scale=1.05
    )

    # ROI 안의 사람 수 계산
    people_in_roi = 0
    for (x, y, w, h) in boxes:
        person_center = (x + w // 2, y + h // 2)
        if (roi_top_left[0] <= person_center[0] <= roi_bottom_right[0] and
                roi_top_left[1] <= person_center[1] <= roi_bottom_right[1]):
            people_in_roi += 1
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        else:
            cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 0, 255), 2)

    # 5초 간격으로 서버 전송
    current_time = time.time()
    if current_time - last_sent_time >= 5:
        try:
            response = requests.post(server_url, json={"count": people_in_roi})
            if response.status_code == 200:
                logger.info(f"Count sent successfully: {people_in_roi}")
            else:
                logger.error(f"Failed to send count: {response.text}")
        except Exception as e:
            logger.error(f"Error sending count to server: {e}")
        last_sent_time = current_time  # 마지막 전송 시간 갱신

    # 화면 출력
    cv2.putText(frame, f"In ROI: {people_in_roi}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)
    cv2.imshow("ROI People Counting", frame)

    # FPS에 맞게 대기 시간 설정
    if cv2.waitKey(int(1000 / fps)) & 0xFF == 27:  # ESC 키로 종료
        break

# 리소스 해제
cap.release()
cv2.destroyAllWindows()
