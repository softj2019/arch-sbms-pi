from dotenv import load_dotenv
import os
import cv2
from flask import Flask, Response
import urllib.parse

# 환경 변수 로드
load_dotenv()
app = Flask(__name__)

# RTSP 설정
IP_OPENCV = os.getenv('IP_OPENCV')
USERNAME_OPENCV = os.getenv('USERNAME_OPENCV')
PASSWORD_OPENCV = os.getenv('PASSWORD_OPENCV')
encoded_password = urllib.parse.quote(PASSWORD_OPENCV)
RTSP_URL = f"rtsp://{USERNAME_OPENCV}:{encoded_password}@{IP_OPENCV}:554/stream2"

def generate_frames():
    cap = cv2.VideoCapture(RTSP_URL, cv2.CAP_FFMPEG)

    # 최신 프레임 유지 설정
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    while True:
        cap.grab()  # 이전 프레임 제거
        success, frame = cap.retrieve()
        if not success:
            break

        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 40])  # 품질 최적화
        frame_bytes = buffer.tobytes()

        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')

@app.route('/video_feed')
def video_feed():
    return Response(generate_frames(), mimetype='multipart/x-mixed-replace; boundary=frame')

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5200, threaded=True)
