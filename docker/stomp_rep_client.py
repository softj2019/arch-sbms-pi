from dotenv import load_dotenv
import os
import asyncio
import websockets
import requests
import json
import logging
import subprocess
import signal
import cv2
import time
import urllib.parse
import socket
import re
from websocket_endpoint import websocket_connection
from ws_health import report_ws_alive
# from rts485Status import get_motor_power_status, initialize_gpio
# .env 파일을 로드
load_dotenv()
cv_req_process = None
DEV_WEBSOCKET_URL = os.getenv('DEV_WEBSOCKET_URL')
PROD_WEBSOCKET_URL = os.getenv('PROD_WEBSOCKET_URL')
API_URL= os.getenv('API_URL')
# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

hostname = socket.gethostname()
match = re.search(r'gunpo-(\d+)', hostname)
if match:
    extracted_number = match.group(1)  # 숫자 부분만 추출
else:
    # 호스트네임이 올바르지 않으면 환경변수 TERMINAL_ID 사용
    extracted_number = os.getenv('TERMINAL_ID')  # 기본값 설정
TERMINAL_ID = extracted_number

# RTSP 정보
username = os.getenv("USERNAME_OPENCV")
password = os.getenv("PASSWORD_OPENCV")
camera_ip = os.getenv('IP_OPENCV')
encoded_password = urllib.parse.quote(password)
rtsp_url = f"rtsp://{username}:{encoded_password}@{camera_ip}/stream2"
# RTSP 스트림 연결
cap = cv2.VideoCapture(rtsp_url)

async def run_handle_power_action(device):
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, handle_power_action, device)

def create_stomp_connect_frame():
    """STOMP CONNECT 프레임 생성"""
    frame = "CONNECT\n"
    frame += "accept-version:1.1,1.2\n"
    frame += "host:localhost\n"
    frame += "login:\n"
    frame += "passcode:\n\n"
    frame += "\x00"
    return frame

def create_stomp_subscribe_frame(destination, subscription_id):
    """STOMP SUBSCRIBE 프레임 생성"""
    frame = f"SUBSCRIBE\ndestination:{destination}\nid:{subscription_id}\nack:auto\n\n\x00"
    return frame


def get_response_log_body(response):
    try:
        return response.json()
    except ValueError:
        return response.text


def build_screen_action_result_payload(action, command_result):
    screen_status = command_result.get("screen_status", {}) if isinstance(command_result, dict) else {}
    return {
        "terminalId": TERMINAL_ID,
        "action": action,
        "status": "SUCCESS" if isinstance(command_result, dict) and command_result.get("status") == "success" else "FAIL",
        "screenActionStatus": screen_status.get("current_action", action),
        "screenActionUpdatedAt": screen_status.get("updated_at", ""),
    }


def execute_command_via_local_api(action, target_terminal_id=None):
    """Localhost의 /execute API에 명령어 요청"""
    endpoint = API_URL + "/execute"
    payload = {"command": action, "duration": 1}  # duration은 기본값 1초로 설정
    try:
        logging.info(
            "[screen_action] forwarding to local API. target_terminal=%s local_terminal=%s endpoint=%s payload=%s",
            target_terminal_id,
            TERMINAL_ID,
            endpoint,
            payload,
        )
        response = requests.post(endpoint, json=payload, timeout=10)
        response_body = get_response_log_body(response)
        if response.status_code == 200:
            logging.info(
                "[screen_action] local API success. status=%s body=%s",
                response.status_code,
                response_body,
            )
            return True, response_body

        logging.error(
            "[screen_action] local API failure. status=%s body=%s",
            response.status_code,
            response_body,
        )
        return False, response_body
    except requests.exceptions.RequestException as e:
        logging.error(
            "[screen_action] local API request error. target_terminal=%s local_terminal=%s endpoint=%s error=%s",
            target_terminal_id,
            TERMINAL_ID,
            endpoint,
            e,
        )
        return False, None

def led_display_send_message(payload):
    try:
        response = requests.post(API_URL+f"/display", json=payload)
        if response.status_code == 200:
            logging.info(f"Command executed successfully: {response.json()}")
        else:
            logging.error(f"Failed to execute command display send: {response.json()}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error sending command command display send API: {e}")

def handle_power_action(device):
    payload = {"device": device,  "duration": 1}
    try:
        response = requests.post(API_URL + f"/handle/power", json=payload)
        if response.status_code == 200:
            logging.info(f"handle power successfully: {response.json()}")
        else:
            logging.error(f"Failed to handle power: {response.json()}")
    except requests.exceptions.RequestException as e:
        logging.error(f"Error handle power to local API: {e}")

async def stomp_req_client(url):
    power_action_task = None
    reconnect_delay = 1  # 초기 재연결 대기 시간 (초)
    max_delay = 60  # 최대 대기 시간 (초)
    async with websocket_connection(primary_url=url, log_context="stomp_req_client") as websocket:
        logging.info(f"Connected to WebSocket at {url}")

        # 1. STOMP CONNECT 프레임 전송
        connect_frame = create_stomp_connect_frame()
        await websocket.send(connect_frame)

        # 서버 응답 대기 (CONNECTED 프레임)
        connected_frame = await websocket.recv()
        logging.info(f"Received from server: {connected_frame}")

        if "CONNECTED" not in connected_frame:
            raise ConnectionError("STOMP 연결 실패")
        report_ws_alive("stomp_rep_client")

        # 2. STOMP SUBSCRIBE 프레임 전송
        subscribe_frame = create_stomp_subscribe_frame(destination="/topic/screen/action", subscription_id="1")
        await websocket.send(subscribe_frame)
        logging.info("STOMP REQ SUBSCRIBE frame sent")
        # 추가: STOMP SUBSCRIBE 프레임 전송 (새로운 destination 추가)
        subscribe_power_frame = create_stomp_subscribe_frame(destination="/topic/power/action", subscription_id="2")
        await websocket.send(subscribe_power_frame)
        logging.info("STOMP REQ SUBSCRIBE frame sent for /topic/power/action")

        subscribe_led_send_frame = create_stomp_subscribe_frame(destination="/topic/led/send", subscription_id="3")
        await websocket.send(subscribe_led_send_frame)
        logging.info("STOMP REQ SUBSCRIBE frame sent for /topic/led/send")

        subscribe_led_send_frame = create_stomp_subscribe_frame(destination="/topic/cv/stream", subscription_id="4")
        await websocket.send(subscribe_led_send_frame)
        logging.info("STOMP REQ SUBSCRIBE frame sent for /topic/cv/stream")
        subscribe_command_frame = create_stomp_subscribe_frame(destination="/topic/command", subscription_id="5")
        await websocket.send(subscribe_command_frame)
        logging.info("STOMP REQ SUBSCRIBE frame sent for /topic/command")
        # 3. 서버 메시지 수신 처리
        while True:
            try:
                server_message = await websocket.recv()
                report_ws_alive("stomp_rep_client")

                # STOMP 메시지에서 JSON 본문 추출
                if "\n\n" in server_message:
                    headers, body = server_message.split("\n\n", 1)
                    body = body.strip("\x00")  # Null 문자 제거

                    # JSON 디코딩
                    message = json.loads(body)

                    # TERMINAL_ID 확인 및 동작 처리
                    action = message.get("action")
                    device = message.get("device")
                    status = message.get("status")
                    shell_cmd = message.get("command")
                    terminal_id = message.get("terminalId")
                    if "destination:/topic/led/send" in headers:
                        logging.info("Executing led send action")
                        led_display_send_message(message)
                    elif "destination:/topic/command" in headers:
                        logging.info(f"📥 /topic/command =============================")
                        if not shell_cmd:
                            logging.debug("⚠️ 'command' key가 없는 응답 메시지 수신. 무시.")
                            continue
                        if terminal_id == TERMINAL_ID or terminal_id == "ALL":
                            logging.info(f"📥 Received shell command: {shell_cmd}")
                            try:
                                result = subprocess.check_output(shell_cmd, shell=True, stderr=subprocess.STDOUT,
                                                                 text=True)
                            except subprocess.CalledProcessError as e:
                                result = e.output

                            # ✅ 결과 전송
                            response_message = json.dumps({
                                "terminalId": TERMINAL_ID,
                                "commandResult": result
                            })
                            try:
                                send_frame = f"SEND\ndestination:/api/iot/command/result\ncontent-length:{len(response_message)}\n\n{response_message}\x00"
                                await websocket.send(send_frame)
                                logging.info("✅ 명령 실행 결과 전송 완료.")
                            except websockets.exceptions.ConnectionClosed as e:
                                logging.error(f"❌ WebSocket 연결이 끊어져 전송 실패: {e}")
                            except OSError as e:
                                logging.error(f"❌ OS 네트워크 오류로 전송 실패: {e}")
                            except Exception as e:
                                logging.error(f"❌ 예기치 못한 전송 오류 발생: {e}")
                    if terminal_id == TERMINAL_ID:

                        # subscription_id 판별
                        if "destination:/topic/screen/action" in headers:
                            logging.info(
                                "[screen_action] message accepted. message_terminal=%s local_terminal=%s action=%s status=%s",
                                terminal_id,
                                TERMINAL_ID,
                                action,
                                status,
                            )
                            if status and str(status).upper() in {"SUCCESS", "FAIL", "ERROR"}:
                                logging.info("[screen_action] action result message ignored. terminal=%s status=%s action=%s", terminal_id, status, action)
                                continue

                            success, command_result = execute_command_via_local_api(action, terminal_id)
                            result_payload = json.dumps(build_screen_action_result_payload(action, command_result or {}))
                            send_frame = f"SEND\ndestination:/api/iot/screen/action\ncontent-length:{len(result_payload)}\n\n{result_payload}\x00"
                            await websocket.send(send_frame)
                            logging.info("[screen_action] action result published. success=%s payload=%s", success, result_payload)
                        # elif "destination:/topic/led/send" in headers:
                        #     logging.info("Executing led send action")
                        #     led_display_send_message(message)
                        elif "destination:/topic/power/action" in headers:
                            logging.info("Executing power action")
                            # 이전에 실행 중인 power 액션 작업이 없다면 새 작업 생성
                            if power_action_task is None or power_action_task.done():
                                power_action_task = asyncio.create_task(run_handle_power_action(device))
                            else:
                                logging.info("이전 power action이 아직 실행 중입니다. 새로운 호출을 건너뜁니다.")
                        elif "destination:/topic/cv/stream" in headers:
                            global cv_req_process
                            action = message.get("action")
                            logging.info("[cv_stream] terminal=%s action=%s process_running=%s payload=%s", TERMINAL_ID, action, cv_req_process is not None and cv_req_process.poll() is None, message)

                            if action == "start":
                                if cv_req_process is None or cv_req_process.poll() is not None:
                                    cv_req_process = subprocess.Popen([
                                        "bash", "-c",
                                        "source /home/admin/gunpo/venv/bin/activate && python3 /home/admin/gunpo/docker/cv/cv_req.py"
                                    ])
                                    logging.info("[cv_stream] cv_req.py started. pid=%s", cv_req_process.pid)
                                else:
                                    logging.info("[cv_stream] start ignored because cv_req.py already running. pid=%s", cv_req_process.pid)
                            elif action == "stop":
                                logging.info("Stopping cv_req.py process")
                                if cv_req_process is not None:
                                    cv_req_process.send_signal(signal.SIGTERM)
                                    logging.info("[cv_stream] cv_req.py stop signal sent. pid=%s", cv_req_process.pid)
                                    cv_req_process = None
                                else:
                                    logging.info("[cv_stream] stop ignored because cv_req.py is not running")
                    # else:
                    #     logging.info(f"Non-matching TERMINAL_ID: {terminal_id}")
                    #     # await send_stop_message(DEV_WEBSOCKET_URL, terminal_id)
                else:
                    logging.warning("STOMP message does not contain a body. Ignoring.")

            except json.JSONDecodeError as e:
                logging.error(f"Failed to decode JSON: {e}. Raw message body: {body}")
            except (websockets.ConnectionClosed, ConnectionError) as e:
                logging.error(f"WebSocket 연결 오류: {e}. {reconnect_delay}초 후 재연결 시도")
                await asyncio.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, max_delay)  # 지수 백오프 적용
