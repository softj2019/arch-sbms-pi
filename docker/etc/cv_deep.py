import os
import cv2
import logging
import urllib.parse
import numpy as np
from dotenv import load_dotenv

# .env 파일 경로
env_file = ".env"

# .env 파일이 없으면 기본값으로 생성
if not os.path.exists(env_file):
    with open(env_file, "w") as file:
        file.write("IP_OPENCV=192.168.10.110\n")
        file.write("USERNAME_OPENCV=admin\n")
        file.write("PASSWORD_OPENCV=1234admin#\n")

# .env 파일 로드
load_dotenv(env_file)

# 환경 변수 가져오기
env_vars = {
    "IP_OPENCV": os.getenv("IP_OPENCV", "192.168.10.110"),
    "USERNAME_OPENCV": os.getenv("USERNAME_OPENCV", "admin"),
    "PASSWORD_OPENCV": os.getenv("PASSWORD_OPENCV", "1234admin#"),
}

# 환경 변수 확인 및 업데이트
def ask_and_update_env():
    updated_vars = {}
    for key, value in env_vars.items():
        new_value = input(f"{key} (현재값: {value}) 변경하려면 입력, 유지하려면 Enter: ")
        updated_vars[key] = new_value if new_value else value

    # .env 파일 업데이트
    with open(env_file, "w") as file:
        for key, value in updated_vars.items():
            file.write(f"{key}={value}\n")
    return updated_vars


# 입체감 필터링 (그림자 + 질감 분석)
def apply_shadow_texture_filter(frame):
    # 그림자 감지 (YCrCb 색 공간 변환)
    ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
    _, shadow_mask = cv2.threshold(ycrcb[:, :, 0], 100, 255, cv2.THRESH_BINARY)

    # 질감 분석 (Sobel 필터)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Sobel(gray, cv2.CV_64F, 1, 1, ksize=5)

    # 그림자가 있는 영역에서 질감 확인 → 벽보(평면)는 제거
    combined_mask = cv2.bitwise_and(shadow_mask, edges.astype(np.uint8))

    return combined_mask


# RTSP 스트리밍 실행 함수
def run_opencv_stream(ip, username, password):
    # 로깅 설정
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
    logger = logging.getLogger()

    # RTSP URL 설정 (비밀번호 인코딩 처리)
    encoded_password = urllib.parse.quote(password)
    rtsp_url = f"rtsp://{username}:{encoded_password}@{ip}:554/stream1"
    logger.info(f"📡 RTSP URL: {rtsp_url}")

    # RTSP 스트림 연결
    cap = cv2.VideoCapture(rtsp_url)

    if not cap.isOpened():
        logger.error("run_opencv_stream: RTSP 스트림에 연결할 수 없습니다.")
        exit()

    logger.info("run_opencv_stream: RTSP 스트림에 성공적으로 연결되었습니다.")

    # 영상 스트리밍 실행
    while True:
        ret, frame = cap.read()
        if not ret:
            logger.error("run_opencv_stream: RTSP 프레임 읽기 실패.")
            break

        # 프레임 크기 조정
        frame_resized = cv2.resize(frame, (640, 480))

        # 입체감 필터링 적용
        filtered_frame = apply_shadow_texture_filter(frame_resized)

        # 영상 출력
        cv2.imshow("RTSP Video Stream", frame_resized)
        cv2.imshow("Filtered Shadow + Texture", filtered_frame)

        # ESC 키로 종료
        if cv2.waitKey(1) & 0xFF == 27:
            break

    # 리소스 해제
    cap.release()
    cv2.destroyAllWindows()


# .env 업데이트 및 OpenCV 실행
if __name__ == "__main__":
    updated_vars = ask_and_update_env()  # 사용자 입력 받기
    run_opencv_stream(
        ip=updated_vars["IP_OPENCV"],
        username=updated_vars["USERNAME_OPENCV"],
        password=updated_vars["PASSWORD_OPENCV"],
    )
