import os
from dotenv import load_dotenv
import cv2
import logging
import urllib.parse

# .env 파일 로드
env_file = '.env'
if not os.path.exists(env_file):
    # .env 파일이 없으면 기본값으로 생성
    with open(env_file, 'w') as file:
        file.write("IP_OPENCV=192.168.10.110\n")
        file.write("USERNAME_OPENCV=admin\n")
        file.write("PASSWORD_OPENCV=1234admin#\n")

load_dotenv(env_file)

# 환경 변수 가져오기
env_vars = {
    "IP_OPENCV": os.getenv('IP_OPENCV', '192.168.10.110'),
    "USERNAME_OPENCV": os.getenv('USERNAME_OPENCV', 'admin'),
    "PASSWORD_OPENCV": os.getenv('PASSWORD_OPENCV', '1234admin#')
}


# 환경 변수 보여주고 변경할지 물어보기
def ask_and_update_env():
    updated_vars = {}
    print("\n현재 환경 변수 값:")
    for key, value in env_vars.items():
        new_value = input(f"{key} (현재값: {value}) 변경하려면 입력, 유지하려면 Enter: ")
        updated_vars[key] = new_value if new_value else value

    # .env 파일 업데이트
    with open(env_file, 'w') as file:
        for key, value in updated_vars.items():
            file.write(f"{key}={value}\n")

    print("\n.env 파일이 업데이트되었습니다.")
    print(updated_vars)
    return updated_vars


# RTSP 스트리밍 실행
def run_opencv_stream(ip, username, password):
    # 로깅 설정
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
    logger = logging.getLogger()

    # RTSP 정보 설정
    encoded_password = urllib.parse.quote(password)
    rtsp_url = f"rtsp://{username}:{encoded_password}@{ip}:554/stream2"
    logger.info(f"RTSP URL: {rtsp_url}")

    # RTSP 스트림 연결
    cap = cv2.VideoCapture(rtsp_url)

    if not cap.isOpened():
        logger.error("RTSP 스트림에 연결할 수 없습니다.")
        exit()

    logger.info("RTSP 스트림에 성공적으로 연결되었습니다.")

    # 영상 스트리밍 실행
    while True:
        ret, frame = cap.read()
        if not ret:
            logger.error("RTSP 프레임 읽기 실패.")
            break

        # 프레임 크기 조정
        frame = cv2.resize(frame, (640, 480))

        # 영상 출력
        cv2.imshow("RTSP Video Stream", frame)

        # ESC 키로 종료
        if cv2.waitKey(1) & 0xFF == 27:
            break

    # 리소스 해제
    cap.release()
    cv2.destroyAllWindows()


# .env 업데이트 및 OpenCV 스크립트 실행
if __name__ == "__main__":
    updated_vars = ask_and_update_env()
    run_opencv_stream(
        ip=updated_vars["IP_OPENCV"],
        username=updated_vars["USERNAME_OPENCV"],
        password=updated_vars["PASSWORD_OPENCV"]
    )
