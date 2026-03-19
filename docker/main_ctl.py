from datetime import datetime, timedelta
import websockets
import RPi.GPIO as GPIO
import time
from flask import Flask, request, jsonify
import serial
import logging
import psutil
import multiprocessing
from dotenv import load_dotenv, dotenv_values
import os
import re
import socket
import json
import signal
import requests
import threading
from typing import TypedDict
from logging_handler import setup_logging

# .env 파일을 로드
load_dotenv()
ip_address_light = os.getenv("IP_ADDRESS_LED")
ip_address_fan = os.getenv("IP_ADDRESS_FAN")

from queue import Queue
from stomp_client import stomp_client
from stomp_rep_client import stomp_req_client
import asyncio
from tapo_on import get_device_info, device_on, device_off
import subprocess
from functools import lru_cache
from network_probe import collect_network_status
from network_resilience import build_runtime_fields
from websocket_endpoint import select_primary_websocket_url, websocket_connection
from ws_health import is_ws_healthy, get_ws_health

# Flask 애플리케이션 초기화
app = Flask(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

# 특정 요청을 스킵할 엔드포인트 리스트
# SKIP_LOG_ENDPOINTS = ["/serial_status"]
SKIP_LOG_ENDPOINTS = ["/serial_status"]
display_thread = None
restart_display_thread = None
display_thread_stop = threading.Event()
message_thread = None
message_thread_stop = threading.Event()
people_count = 0

# Flask 로그에서 특정 end point 요청을 무시하는 filter
class EndpointFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        for endpoint in SKIP_LOG_ENDPOINTS:
            if endpoint in msg:
                return False  # 로그 스킵
        return True  # 로그 출력

# Flask 기본 로거에 필터 적용
log = logging.getLogger("werkzeug")
log.addFilter(EndpointFilter())

# 호스트네임 할당
hostname = socket.gethostname()
match = re.search(r'gunpo-(\d+)', hostname)
if match:
    extracted_number = match.group(1)  # 숫자 부분만 추출
else:
    extracted_number = os.getenv('TERMINAL_ID')  # 기본값 설정

# WebSocket URL
PROD_WEBSOCKET_URL = select_primary_websocket_url(extracted_number)

# 접속단말기가 설치된 정류장 ID 할당
TERMINAL_ID = extracted_number
logging.info(f"TERMINAL_ID {TERMINAL_ID}")

# 시리얼 포트 설정
SERIAL_PORT = '/dev/ttyUSB0'
BAUD_RATE = 115200

# M10 프로토콜 명령어
POWER_ON_CMD = bytes.fromhex('02 86 0A 00 50 00 4F 00 57 00 3D 00 31 00 F6 03')  # 파워 ON
POWER_OFF_CMD = bytes.fromhex('02 86 0A 00 50 00 4F 00 57 00 3D 00 30 00 F5 03')  # 파워 OFF

# 기본값
UP_PIN = 26
DOWN_PIN = 20
STOP_PIN = 21

PINS = [26, 20, 21, 2, 3, 4, 17, 27, 22, 10, 9, 11, 5, 6, 13, 19, 26, 21]

# 경고 메시지 비활성화
GPIO.setwarnings(False)

# Broadcom 칩셋의 GPIO 핀 번호를 사용하여 핀을 제어합니다.
GPIO.setmode(GPIO.BCM)

for pin in PINS:
    GPIO.setup(pin, GPIO.OUT)
    GPIO.output(pin, GPIO.HIGH)
# GPIO 핀 초기화
# GPIO.setup(UP_PIN, GPIO.OUT, initial=GPIO.LOW)
# GPIO.setup(DOWN_PIN, GPIO.OUT, initial=GPIO.LOW)
# GPIO.setup(STOP_PIN, GPIO.OUT, initial=GPIO.LOW)

# Flask와 WebSocket 간 데이터 공유 큐
data_queue = Queue()
# 인원수 저장 변수
detected_people_count = 0
# 재실 감지로 인한 스크린 제어 상태를 STOP 을 제외하고 저장
last_screen_action = ""
current_screen_action = "STOP"
current_screen_action_updated_at = datetime.now().isoformat(timespec="seconds")
# 재실 감지로 인한 스크린 제어 진행여부
cv_count_screen_action = 0

emergency_message_status = 0
stop_event = threading.Event()  # 중단 이벤트
led_state = "OFF"

# .env_custom 파일 불러오기
project_root = os.path.abspath(os.path.dirname(__file__))
custom_env_path = os.path.join(project_root, ".env_custom")
custom_env = dotenv_values(custom_env_path)

for key, value in custom_env.items():
    os.environ[key] = value

class ConfigCache(TypedDict):
    ledLiteOnTime: str
    ledLiteOffTime: str
    ledFontColor: str
    ledMessage: str
    fanTemperature: str
    allowIpList: str
    t1h: str

config_cache: ConfigCache = {}
config_cache.update({
    "ledLiteOnTime": "17:00",
    "ledLiteOffTime": "04:00",
    "fanTemperature": "24.0",
    "t1h": "0.0",
})
config_lock = threading.Lock()

# tapo 제어
async def set_tapo_power_if_needed(ip, turn_on: bool, device_name: str = "Tapo"):
    try:
        device_status = await get_device_info(ip)
        if turn_on and not device_status.device_on:
            await device_on(ip)
            logging.info(f"set_tapo_power_if_needed: {device_name} 전원 ON")
        elif not turn_on and device_status.device_on:
            await device_off(ip)
            logging.info(f"set_tapo_power_if_needed: {device_name} 전원 OFF")
        else:
            logging.info(f"set_tapo_power_if_needed: {device_name} 제어 불필요 (이미 {'ON' if turn_on else 'OFF'})")
    except Exception as e:
        logging.error(f"set_tapo_power_if_needed: {device_name} 제어 실패: {e}")

# fan 제어
def start_fan_auto_control():
    global config_cache, ip_address_fan

    async def fan_control_loop():
        while True:
            try:
                t1h = float(config_cache.get("t1h", "0"))
                fan_temp = float(config_cache.get("fanTemperature", "100"))

                if t1h > fan_temp:
                    logging.info(f"start_fan_auto_control: 외부 온도({t1h}°C) > 기준 온도({fan_temp}°C) → 팬 ON")
                    await set_tapo_power_if_needed(ip_address_fan, True, "팬")
                else:
                    logging.info(f"start_fan_auto_control: 외부 온도({t1h}°C) ≤ 기준 온도({fan_temp}°C) → 팬 OFF")
                    await set_tapo_power_if_needed(ip_address_fan, False, "팬")
            except Exception as e:
                logging.error(f"start_fan_auto_control: 팬 자동 제어 오류: {e}")
            await asyncio.sleep(10)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(fan_control_loop())

# 유니코드 디코딩
def get_decoded_message(raw_message: str | None) -> str:
    if not raw_message:
        return "승차대기"

    # 유니코드 이스케이프가 남아있으면 디코딩 시도
    if "\\u" in raw_message:
        try:
            return bytes(raw_message, 'utf-8').decode('unicode_escape')
        except Exception as e:
            logging.warning(f"get_decoded_message: 유니코드 디코딩 실패: {e}")
    return raw_message


# 30초 추기로 STOMP 기반 설정값 업데이트
async def fetch_config_every_30s(ws_url):
    global config_cache
    try:
        async with websocket_connection(primary_url=ws_url, log_context="fetch_config_every_30s") as websocket:

            await websocket.send("CONNECT\naccept-version:1.2\n\n\x00")
            await websocket.send("SUBSCRIBE\ndestination:/topic/config\nid:sub-config\n\n\x00")
            while True:
                try:
                    await websocket.send("SEND\ndestination:/api/iot/config\ncontent-type:application/json\n\n{}\x00")
                    message = await asyncio.wait_for(websocket.recv(), timeout=10)
                    parts = message.split("\n\n")

                    # json 파싱 후 캐싱
                    if len(parts) > 1:
                        body = parts[1].replace('\x00', '').strip()
                        if body.startswith('{') and body.endswith('}'):
                            try:
                                config_data = json.loads(body)
                                config_cache.update(config_data)
                            except json.JSONDecodeError as e:
                                logging.warning(f"fetch_config_every_30s: JSON 파싱 실패: {e} / 본문: {body}")
                        else:
                            logging.debug(f"fetch_config_every_30s: 메시지 본문이 JSON 아님. 무시: {body}")
                    else:
                        logging.debug("fetch_config_every_30s： 본문이 없는 STOMP 프레임. 무시.")

                except asyncio.TimeoutError:
                    logging.warning("fetch_config_every_30s: 10초 응답 없음. 다음 요청 대기 중...")
                await asyncio.sleep(30)  # 30초마다 재요청

    except Exception as e:
        logging.error(f"fetch_config_every_30s: 설정값 WebSocket 오류: {e}")
        await asyncio.sleep(30)

# 환경설정 불러오기
def start_config_fetch_loop():
    while True:
        try:
            asyncio.run(fetch_config_every_30s(PROD_WEBSOCKET_URL))
        except Exception as e:
            if extracted_number != os.getenv('OFFICE_HOSTNAME'):
                logging.error(f"start_config_fetch_loop: fetch_config_every_30s 재시도 필요: {e}")

            time.sleep(30)  # 30초 후 재시도

# 전역 config_cache 에서 ledLiteOnTime, ledLiteOffTime 가져오기
def get_on_off_times():
    global config_cache
    on_time = config_cache.get("ledLiteOnTime", "00:00")
    off_time = config_cache.get("ledLiteOffTime", "00:00")

    return on_time, off_time

# 현시간이 설정시간과 일치하는지 확인
def check_time(target_time):
    now = datetime.now().strftime("%H:%M")
    return now >= target_time


def is_between_times(on_time_str, off_time_str):
    now = datetime.now().time()
    on_time = datetime.strptime(on_time_str, "%H:%M").time()
    off_time = datetime.strptime(off_time_str, "%H:%M").time()

    # 밤 -> 새벽으로 넘어가는 경우 처리
    if on_time < off_time:
        return on_time <= now < off_time  # 같은 날
    else:
        return now >= on_time or now < off_time  # 자정을 넘김


def check_time_reached(target_time_str):
    """설정된 시간 이상인지 확인"""
    now = datetime.now().time()
    target_time = datetime.strptime(target_time_str, "%H:%M").time()
    return now >= target_time

# 서버에서 설정된 시간에 맞춰 장치 on/off 하는 함수
async def schedule_device_control(ip):
    if not ip:
        logging.error("schedule_device_control: TAPO_DEVICE_IP 없음 -> .env 확인필요")
        return

    while True:
        on_time, off_time = get_on_off_times()
        try:
            device_status = await get_device_info(ip)
        except Exception as e:
            logging.error(f"schedule_device_control: 장치 상태 확인 실패: {e}")
            await asyncio.sleep(10)
            continue

        if ip.endswith("103"):
            device_name = "LED"
            # 장치 on/off
            if is_between_times(on_time, off_time):
                # 켜야 할 시간대
                if not device_status.device_on:
                    await set_tapo_power_if_needed(ip, True, "LED")
                    logging.info(f"schedule_device_control: {device_name} ON: (시간: {on_time} ~ {off_time})")
            else:
                # 꺼야 할 시간대
                if device_status.device_on:
                    # await device_off(ip)
                    await set_tapo_power_if_needed(ip, False, "LED")
                    logging.info(f"schedule_device_control {device_name} OFF: 시간: {off_time} ~ {on_time})")
        elif ip.endswith("104"):
            # fan 의 경우 시간에 따른 처리 로직 없음
            device_name = "FAN"
        else:
            device_name = "Unknown"
            logging.error(f"schedule_device_control: ip 이상: {ip}")

        await asyncio.sleep(3)

# 비동기 루프를 실행하는 스레드
def start_async_loop():
    global ip_address_light
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(schedule_device_control(ip_address_light))

# led 토글
def toggle_led():
    global led_state
    if led_state == "OFF":
        send_command(POWER_ON_CMD)
        led_state = "ON"
        logging.info("toggle_led: LED turned ON")
    else:
        send_command(POWER_OFF_CMD)
        led_state = "OFF"
        logging.info("toggle_led: LED turned OFF")
    return led_state

# 웹소켓 url 에서 ip 주소와 포트 추출
def extract_ip_port(url: str):
    """
    :param url: 웹소켓 URL (예: ws://175.45.215.53:8080/websocket, ws://175.45.215.53/websocket)
    :return: IP와 포트 (예: 175.45.215.53:8080 또는 175.45.215.53)
    """
    match = re.search(r"(\d+\.\d+\.\d+\.\d+)(:\d+)?", url)
    if match:
        ip = match.group(1)  # IP 주소 추출
        port = match.group(2) if match.group(2) else ""  # 포트가 있으면 포함
        return f"{ip}{port}"  # IP만 있으면 IP만 반환, 포트 있으면 IP:포트 반환
    return None

# 크로미움 브라우저 실행 (start_browser.py 실행)
@app.route('/start_browser', methods=['POST'])
def start_browser():
    try:
        subprocess.Popen(["python3", "start_browser.py"])
        return jsonify({"status": "success", "message": "Chromium browser started"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# 크로미움 브라우저 종료(stop_browser.py 실행)
@app.route('/stop_browser', methods=['POST'])
def stop_browser():
    try:
        subprocess.run(["python3", "stop_brower.py"], check=True)
        return jsonify({"status": "success", "message": "Chromium browser stopped"}), 200
    except subprocess.CalledProcessError:
        return jsonify({"status": "error", "message": "No Chromium process found"}), 404

# led 전원 토글
@app.route('/led_power', methods=['POST'])
def led_power():
    try:
        new_state = toggle_led()
        return jsonify({"status": "success", "message": f"LED is now {new_state}"}), 200

    except Exception as e:
        logging.error(f"led_power: Error toggling LED power: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# 시스템 정보 조회
@app.route('/system_info', methods=['GET'])
def get_system_info():
    try:
        # CPU 정보
        cpu_usage = psutil.cpu_percent(interval=1)

        # 메모리 정보
        memory = psutil.virtual_memory()
        total_memory = memory.total / (1024 ** 3)  # GB 단위
        available_memory = memory.available / (1024 ** 3)  # GB 단위
        used_memory = total_memory - available_memory

        # 디스크 정보
        disk = psutil.disk_usage('/')
        total_disk = disk.total / (1024 ** 3)  # GB 단위
        free_disk = disk.free / (1024 ** 3)  # GB 단위
        used_disk = total_disk - free_disk
        network_status = collect_network_status()

        system_info = {
            "cpu_usage": f"{cpu_usage:.2f}%",
            "memory": f"{total_memory:.2f} GB / {used_memory:.2f} GB / {available_memory:.2f} GB",
            "disk": f"{total_disk:.2f} GB / {used_disk:.2f} GB / {free_disk:.2f} GB",
            "lte_router_gateway": network_status.router_gateway or "",
            "lte_router_gateway_status": "ON" if network_status.router_gateway_ok else "OFF",
            "lte_router_link": "ON" if network_status.lte_router_connected else "OFF",
            "lte_router_wan_ip": network_status.router_wan_ip or "",
            "network_outbound": "ON" if network_status.outbound_ok else "OFF",
            "network_health": "ON" if network_status.healthy else "OFF",
            "network_check_required": "Y" if not network_status.healthy else "N",
        }
        system_info.update(build_runtime_fields(network_status, include_pending_events=True))

        return jsonify({"status": "success", "system_info": system_info}), 200
    except Exception as e:
        logging.error(f"Error fetching system info: {e}")
        return jsonify({"status": "error", "message": "Failed to fetch system info"}), 500

# 특정 gpio 핀의 상태를 변경 (on/high, off/low)
@app.route('/gpio_toggle', methods=['POST'])
def gpio_toggle():
    try:
        # JSON 데이터 파싱
        data = request.json
        pin = data.get('pin', None)
        state = data.get('state', None)

        # 유효성 검사
        if pin is None or state not in ['on', 'off']:
            raise ValueError("Invalid input. 'pin' and 'state' (on/off) are required.")

        pin = int(pin)

        # 핀을 출력 모드로 설정
        GPIO.setup(pin, GPIO.OUT)

        # 상태 변경
        if state == 'on':
            GPIO.output(pin, GPIO.HIGH)
            logging.info(f"Pin {pin} set to HIGH")
        else:
            GPIO.output(pin, GPIO.LOW)
            logging.info(f"Pin {pin} set to LOW")

        # 상태 반환
        return jsonify({"status": "success", "pin": pin, "state": state}), 200
    except ValueError as e:
        logging.error(f"Validation error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        return jsonify({"status": "error", "message": "Failed to toggle GPIO pin"}), 500

# 시리얼 통신 상태 점검 및 오류 발생시 시스템 재부팅
def check_serial_connection():
    try:
        # 시리얼 포트 존재 여부 확인
        if not os.path.exists(SERIAL_PORT):
            logging.error(f"check_serial_connection: 시리얼 포트 {SERIAL_PORT}가 존재하지 않습니다.")
            return "ERROR"

        # 포트 점유 여부 확인 (다른 프로세스에 의해 사용 중인지 검사)
        process = subprocess.run(["lsof", SERIAL_PORT], capture_output=True, text=True)
        if process.stdout:
            logging.warning(f"check_serial_connection: 시리얼 포트 {SERIAL_PORT}가 다른 프로세스에 의해 사용 중: {process.stdout}")
            return "BUSY"

        # 시리얼 포트 열기 및 상태 확인
        ser = serial.Serial(SERIAL_PORT, baudrate=BAUD_RATE, timeout=1)
        if ser.is_open:
            ser.close()
            return "ON"
        else:
            return "OFF"

    except serial.SerialException as e:
        logging.error(f"check_serial_connection: 시리얼 통신 오류 발생: {e}")

        # [Errno 5] Input/output error` 발생 시 시스템 자동 재부팅
        if "[Errno 5] Input/output error" in str(e):
            logging.critical("check_serial_connection: 심각한 시리얼 포트 오류 발생. 시스템을 5초 후 자동 재부팅합니다.")
            time.sleep(5)  # 로그 확인을 위해 5초 대기
            os.system("sudo reboot")

        return "ERROR"

# 시리얼 포트상태 확인 api
@app.route('/serial_status', methods=['GET'])
def serial_status():
    try:
        status = check_serial_connection()
        return jsonify({"status": "success", "serial_status": status}), 200
    except Exception as e:
        logging.error(f"Error checking serial status: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# stx 부터 data 까지의 합을 1byte 로 반환
def calculate_checksum(data):
    return sum(data) & 0xFF

# 새로운 템플릿 정의
def encode_to_protocol(message, default_template, color="00", font="00", weight="01", eff="000000000000", ysz="2",
                       fix=1, dly_interval=6):
    STX = 0x02
    ETX = 0x03
    TYPE = 0x84  # 광고 추가
    # template = "LNE=1,YSZ=2,EFF=090009000900,TXT=$C00$F00$W01$A00{}"

    formatted_message = default_template if not message else f"RST=1,LNE=1,FIX={fix},YSZ={ysz},EFF={eff},NEN=0,DLY={dly_interval},TXT=$c{color}$f{font}$w{weight}$A00{message}"
    encoded_data = formatted_message.encode('utf-16le')  # 하위 바이트 우선
    length = len(encoded_data).to_bytes(2, byteorder='little')

    # Header: STX + TYPE + LENGTH
    header = bytes([STX, TYPE]) + length

    # 전체 데이터 구성
    data = header + encoded_data

    # Checksum 계산
    checksum = calculate_checksum(data)

    # 최종 패킷 구성
    command = data + bytes([checksum]) + bytes([ETX])

    # logging.info(f"Encoded command: {command.hex()}")
    return command

serial_lock = threading.Lock()

# 명령어 전달
def send_command(command):
    try:
        with serial_lock:
            with serial.Serial(SERIAL_PORT, baudrate=BAUD_RATE, timeout=0.3) as ser:
                ser.write(command)
                time.sleep(0.3)
                response = ser.read(ser.in_waiting or 128)
                logging.info(f"send_command: Response received ({len(response)} bytes): {response.hex()}")
    except Exception as e:
        logging.error(f"send_command: Serial communication error: {e}")

# 파워 on 명령 전송
def power_on():
    send_command(POWER_ON_CMD)

# 파워 off 명령 전송
def power_off():
    send_command(POWER_OFF_CMD)

def check_pin_states():
    for pin in PINS:
        logging.info(f"Motor states: pin={pin}, st={GPIO.input(pin)}")
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    time.sleep(0.1)

def stop_pins():
    for pin in PINS:
        GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)
    time.sleep(0.1)

    for pin in PINS:
        GPIO.output(pin, GPIO.LOW)  # LOW 상태로 초기화

# 모니터 상태 확인
def get_motor_status():
    try:
        time.sleep(0.1)
        up_state = GPIO.input(UP_PIN)
        down_state = GPIO.input(DOWN_PIN)
        stop_state = GPIO.input(STOP_PIN)

        # 현재 핀 상태 로깅
        logging.info(f"Motor states: UP={up_state}, DOWN={down_state}, STOP={stop_state}")

        # 상태 반환
        return {
            "UP": "HIGH" if up_state == GPIO.HIGH else "LOW",
            "DOWN": "HIGH" if down_state == GPIO.HIGH else "LOW",
            "STOP": "HIGH" if stop_state == GPIO.HIGH else "LOW",
        }
    except Exception as e:
        logging.error(f"Error reading motor status: {e}")
        return {
            "UP": "ERROR",
            "DOWN": "ERROR",
            "STOP": "ERROR",
        }

def get_screen_action_status():
    try:
        motor_status = get_motor_status()
        return {
            "current_action": current_screen_action,
            "last_action": last_screen_action or current_screen_action,
            "updated_at": current_screen_action_updated_at,
            "motor_gpio": motor_status,
        }
    except Exception as e:
        logging.error(f"Error building screen action status: {e}")
        return {
            "current_action": current_screen_action,
            "last_action": last_screen_action or current_screen_action,
            "updated_at": current_screen_action_updated_at,
            "motor_gpio": {
                "UP": "ERROR",
                "DOWN": "ERROR",
                "STOP": "ERROR",
            },
        }

# 명령어 활성 및 gpio 상태 변경
def activate_command(command, duration=0.1):
    global last_screen_action, current_screen_action, current_screen_action_updated_at
    try:
        if command == "UP":
            GPIO.output(UP_PIN, GPIO.LOW)
            time.sleep(duration)
            GPIO.output(UP_PIN, GPIO.HIGH)
            last_screen_action = command
            current_screen_action = command
            current_screen_action_updated_at = datetime.now().isoformat(timespec="seconds")

        elif command == "DOWN":
            GPIO.output(DOWN_PIN, GPIO.LOW)
            time.sleep(duration)
            GPIO.output(DOWN_PIN, GPIO.HIGH)
            last_screen_action = command
            current_screen_action = command
            current_screen_action_updated_at = datetime.now().isoformat(timespec="seconds")


        elif command == "STOP":
            GPIO.output(STOP_PIN, GPIO.LOW)
            time.sleep(duration)
            GPIO.output(STOP_PIN, GPIO.HIGH)
            current_screen_action = command
            current_screen_action_updated_at = datetime.now().isoformat(timespec="seconds")
        else:
            raise ValueError(f"Invalid command: {command}")
    except RuntimeError as e:
        logging.error(f"activate_command: GPIO RuntimeError for command {command}: {e}")
    except ValueError as e:
        logging.error(f"activate_command: Validation error: {e}")
    except Exception as e:
        logging.error(f"activate_command: Unexpected error in activate_command: {e}")

# gpio 상태확인
@app.route('/screen_status', methods=['GET'])
def screen_status():
    try:
        screen_state = get_screen_action_status()
        return jsonify({"status": "success", "screen_status": screen_state}), 200
    except Exception as e:
        logging.error(f"Error reading screen status: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/gpio_status', methods=['GET'])
def gpio_status():
    try:
        # 요청된 핀 번호 가져오기
        pin = request.args.get('pin', type=int)
        if pin is None:
            return jsonify({"status": "error", "message": "Pin number is required"}), 400

        # 핀 모드 설정 (입력 모드, 풀다운 저항 추가)
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

        # 핀 상태 읽기
        state = GPIO.input(pin)
        return jsonify({"status": "success", "pin": pin, "state": state}), 200
    except Exception as e:
        logging.error(f"Error reading GPIO pin {pin}: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/cpu_temp', methods=['GET'])
def get_cpu_temperature():
    try:
        # CPU 온도를 읽음
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            temp = float(f.readline()) / 1000.0  # 온도를 섭씨로 변환
        return jsonify({"status": "success", "cpu_temp": temp}), 200
    except Exception as e:
        logging.error(f"Error reading CPU temperature: {e}")
        return jsonify({"status": "error", "message": "Failed to read CPU temperature"}), 500


@app.route('/led', methods=['POST'])
def led_control():
    data = request.json
    state = data.get('state')
    logging.info(f"power state: {state}")
    if state == 'on':
        power_on()
        return jsonify({"status": "success", "message": "LED power turned on"}), 200
    elif state == 'off':
        power_off()
        return jsonify({"status": "success", "message": "LED power turned off"}), 200
    else:
        return jsonify({"status": "error", "message": "Invalid state"}), 400


def find_chromium_main_pids():
    """Chromium의 메인 프로세스 PIDs를 찾음"""
    main_pids = []
    for process in psutil.process_iter(attrs=['pid', 'name', 'cmdline']):
        try:
            cmd = " ".join(process.info['cmdline']) if process.info['cmdline'] else ""
            if process.info['name'] and "chromium" in process.info['name'].lower():
                if "--kiosk" in cmd or "chromium-browser" in cmd or "/usr/lib/chromium/chromium" in cmd:
                    main_pids.append(process.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return main_pids


def kill_chromium():
    """Chromium의 메인 프로세스를 안전하게 종료"""
    pids = find_chromium_main_pids()

    if not pids:
        print("❌ 실행 중인 Chromium 메인 프로세스를 찾을 수 없습니다.")
        return False

    print(f"🔍 종료할 Chromium 메인 PIDs: {pids}")

    # 1. 안전한 종료 (SIGTERM)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            continue

    # 2. 강제 종료 (SIGKILL) - 3초 후 확인 후 강제 종료
    time.sleep(3)
    pids_after_terminate = find_chromium_main_pids()
    if pids_after_terminate:
        print(f"⚠️ 강제 종료할 Chromium PIDs: {pids_after_terminate}")
        for pid in pids_after_terminate:
            try:
                os.kill(pid, signal.SIGKILL)
                print(f"✅ 강제 종료 완료: PID {pid}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    return True

# 명령어 실행 api
@app.route('/handle/power', methods=['POST'])
def handlePower():
    try:
        data = request.json
        device = data.get('device')
        duration = data.get('duration', 1)  # 기본 동작 시간 1초
        new_state = "OFF"

        if device == "lcd_display":
            try:
                pids_before = find_chromium_main_pids()
                if pids_before and len(pids_before) > 0:
                    # Chromium 종료
                    if kill_chromium():
                        new_state = "OFF"
                    else:
                        return jsonify({"status": "error", "message": "Chromium 종료 실패"}), 500
                else:
                    subprocess.Popen(["python3", "start_browser.py"], stderr=subprocess.PIPE)
                    time.sleep(3)  # 실행 안정성을 위해 대기

                    pids_after = find_chromium_main_pids()
            except Exception as e:
                logging.error(f" Chromium 실행 중 오류 발생: {e}")
                return jsonify({"status": "error", "message": "Chromium 실행 실패"}), 500

        elif device == "led_panel":
            new_state = toggle_led()

        elif device == "led_light":
            try:
                is_on = asyncio.run(get_device_info(ip_address_light))
                if is_on.device_on:
                    asyncio.run(device_off(ip_address_light))
                    new_state = "OFF"
                else:
                    asyncio.run(device_on(ip_address_light))
                    new_state = "ON"
            except Exception as e:
                logging.error(f"Tapo Light 제어 오류: {e}")
                return jsonify({"status": "error", "message": "LED Light 제어 실패"}), 500

        elif device == "fan":
            try:
                fan_is_on = asyncio.run(get_device_info(ip_address_fan))
                if fan_is_on.device_on:
                    asyncio.run(device_off(ip_address_fan))
                    new_state = "OFF"
                else:
                    asyncio.run(device_on(ip_address_fan))
                    new_state = "ON"
                logging.info(f"Tapo 정보: {fan_is_on}")
            except Exception as e:
                logging.error(f"Tapo Fan 제어 오류: {e}")
                return jsonify({"status": "error", "message": "Fan 제어 실패"}), 500

        else:
            return jsonify({"status": "error", "message": "Invalid device"}), 400

        # STOMP 메시지 전송
        try:
            message = json.dumps({
                "status": new_state,
                "device": device,
                "terminalId": TERMINAL_ID
            })
            asyncio.run(send_stomp_message("/topic/power/action", message, PROD_WEBSOCKET_URL))
        except Exception as e:
            logging.error(f" STOMP 메시지 전송 오류: {e}")
            return jsonify({"status": "error", "message": "STOMP 메시지 전송 실패"}), 500

        return jsonify({"status": new_state, "device": device, "duration": duration}), 200

    except Exception as e:
        logging.error(f" handlePower 함수 오류 발생: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# 명령어 실행 api
@app.route('/execute', methods=['POST'])
def execute():
    command = None
    try:
        data = request.json
        command = data.get('command')
        duration = data.get('duration', 1)  # 기본 동작 시간 1초

        # 명령어 실행 로그
        logging.info(f"Executing command: {command} with duration: {duration}s")
        # 명령어 실행
        activate_command(command, duration)
        # 성공 로그
        logging.info(f"Command {command} executed successfully for {duration}s")
        screen_state = get_screen_action_status()
        return jsonify({"status": "success", "command": command, "duration": duration, "screen_status": screen_state}), 200

    except Exception as e:
        # 에러 로그
        logging.error(f"Error while executing command: {command}, Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# openCV 에서 전송된 인원수를 처리하고, 필요 시 led 전광판에 메시지 전송
@app.route('/update_count', methods=['POST'])
def update_count():
    global emergency_message_status, detected_people_count, cv_count_screen_action, last_screen_action, display_thread, config_cache

    if emergency_message_status == 1:
        logging.info("[update_count] Emergency mode activated. Stopping...")
        return jsonify({"status": "error", "message": "Emergency mode activated. Stopping update_count."}), 200
    try:

        # 클라이언트에서 전송된 데이터 처리
        data = request.json
        detected_people_count = data.get('count', 0)

        # 인원수가 0보다 큰 경우 메시지 전송
        if detected_people_count > 0:
            if cv_count_screen_action == 0:
                # "승차대기" 메시지 전송 (최초 감지시에만)
                raw_display_message = config_cache.get("ledMessage")
                display_message = get_decoded_message(raw_display_message)
                display_color = config_cache.get("ledFontColor", "00")
                message = display_message

                color = display_color or '00'
                font = '00'
                weight = '01'
                eff = '090009000900'
                ysz = '2'
                fix = 1
                dly_interval = 60000
                start_message_with_timeout(message, color, font, weight, eff, ysz, fix, dly_interval, 20)

                # 재실인원 최초 감지시에만 모터 STOP 전송
                activate_command("STOP", 0.1)

                stop_message = json.dumps({
                    "action": "STOP",
                    "terminalId": TERMINAL_ID
                })
                cv_count_screen_action = 1
                asyncio.run(send_stomp_message("/topic/screen/action", stop_message, PROD_WEBSOCKET_URL))
                logging.info("STOP message sent to STOMP server.")
            else:
                # cv_count_screen_action==1: 재실감지 유지 중 - 승차대기 유지, 아무것도 안 함
                logging.info("update_count: people detected, waiting message already displayed. skip.")

        else:

            if cv_count_screen_action == 1:
                cv_count_screen_action = 0
                logging.info("update_count: people count cleared, resetting screen action and displaying clock.")

                # 시계 메시지 즉시 표시
                display_thread = threading.Thread(target=display_default_message, daemon=True)
                display_thread.start()

                stop_message = json.dumps({
                    "action": last_screen_action or "STOP",
                    "terminalId": TERMINAL_ID
                })
                asyncio.run(send_stomp_message("/topic/screen/action", stop_message, PROD_WEBSOCKET_URL))
                logging.info("update_count: people count cleared, reset screen action broadcast state.")

        return jsonify({"status": "success", "message": "Count updated"}), 200

    except Exception as e:
        logging.error(f"Error processing count: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# stomp 메세지를 websocket 을 통해 전송
async def send_stomp_message(destination, message, url):
    try:
        async with websocket_connection(primary_url=url, log_context="send_stomp_message") as websocket:
            # STOMP SEND 프레임 생성
            send_frame = f"SEND\ndestination:{destination}\n\n{message}\x00"
            await websocket.send(send_frame)
            logging.info(f"send_stomp_message: stomp 메세지 전송 {destination}: {message}")

    except Exception as e:
        logging.error(f"Failed to send STOMP message: {e}")

# 현재 시간 기준으로 다음 분에 갱신
def display_default_message():
    dly_interval = 60
    global emergency_message_status
    last_sent_minute = None

    try:
        while not stop_event.is_set():
            now = datetime.now()
            current_minute = now.minute

            if current_minute != last_sent_minute:
                next_minute = (now + timedelta(minutes=1)).replace(second=0, microsecond=0)

                hour = now.strftime("%H")
                minute = now.strftime("%M")
                h1, h2 = hour[0], hour[1]
                m1, m2 = minute[0], minute[1]

                default_message = (
                    f"RST=1,LNE=1,YSZ=1,SPD=3,DLY={dly_interval},FIX=1,EFF=090009000900,NEN=0,TXT=$f01$c00 {h2}·{m2} ,"
                    f"RST=1,LNE=2,YSZ=1,SPD=3,DLY={dly_interval},FIX=1,EFF=090009000900,NEN=0,TXT=$f01$c00 {h1}·{m1} "
                )
                logging.info(f"display_default_message: 메시지 갱신: {hour}:{minute}")
                command = encode_to_protocol("", default_message)
                send_command(command)
                last_sent_minute = current_minute

            remaining = (next_minute - datetime.now()).total_seconds() if last_sent_minute == current_minute else 60
            if stop_event.wait(timeout=min(remaining, 1)):
                return

    except Exception as e:
        logging.error(f"Error displaying default message: {e}")

# 메세지를 일정시간 유지 후 갱신하는 스레드 함수
def start_message_with_timeout(message, color="00", font="00", weight="01", eff="090009000900", ysz="2", fix=1,
                               dly_interval=60000, duration=60):
    def message_worker():
        start_time = datetime.now()
        logging.info(f"start_message_with_timeout: 메시지 스레드 시작됨: '{message}' (유지시간: {duration}s)")

        command = encode_to_protocol(message, "", color, font, weight, eff, ysz, fix, dly_interval)
        send_command(command)
        logging.info(f"start_message_with_timeout: 메시지 전송 완료: '{message}'")

        # 2. 설정된 유지 시간 동안 대기
        while not message_thread_stop.is_set():
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed > duration:
                message_thread_stop.set()
                logging.info(f"start_message_with_timeout: 메시지 유지시간 초과됨, 다시 전송 중: '{message}'")

                # display_default_message() 실행
                global display_thread
                display_thread = threading.Thread(target=display_default_message, daemon=True)
                display_thread.start()
                break

            time.sleep(1)

    global message_thread
    if message_thread and message_thread.is_alive():
        logging.info("start_message_with_timeout: 메시지 스레드가 이미 실행 중입니다. 새로 실행하지 않음.")
        return

    # 기존 중단 이벤트 초기화 후 스레드 시작
    message_thread_stop.clear()
    message_thread = threading.Thread(target=message_worker, daemon=True)
    message_thread.start()

# 기본메세지를 일정 시간 후 강제 재시작
def restart_display_default_message(duration):
    def delayed_start():
        start_time = datetime.now()

        # 2. 설정된 유지 시간 동안 대기
        while not display_thread_stop.is_set():
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed > duration:
                display_thread_stop.set()
                logging.info(f"restart_display_default_message: 시간 초과됨, LED 시계 다시 전송 중 ")
                display_thread = threading.Thread(target=display_default_message, daemon=True)
                display_thread.start()
                start_time = datetime.now()  # 갱신 시점 리셋
            time.sleep(1)

    global restart_display_thread, people_count
    if restart_display_thread and restart_display_thread.is_alive():
        logging.info("restart_display_default_message: display_thread 이미 실행 중입니다. 새로 실행하지 않음.")
        return
    display_thread_stop.clear()
    restart_display_thread = threading.Thread(target=delayed_start, daemon=True)
    restart_display_thread.start()

@app.route('/display', methods=['POST'])
def display():
    global emergency_message_status, display_thread
    try:
        # JSON 데이터 파싱
        data = request.json
        if not data:
            raise ValueError("No JSON payload provided")

            # emergency_message_status 값을 정수형(int)으로 변환
        try:
            emergency_message_status = int(data.get("emergencyMessageStatus", 0))
        except (ValueError, TypeError):
            return jsonify({"status": "error", "message": "Invalid emergencyMessageStatus type"}), 400

        # 긴급 메시지 활성화 처리
        if emergency_message_status == 1:
            logging.info("[display] 긴급 모드 활성화, 기본 메시지 중단")
            stop_event.set()  # 기본 메시지 및 인원수 업데이트 중단

            message = data.get('message', '') or data.get('sendMessage', '')
            color = data.get('color', '00')
            font = data.get('font', '00')
            weight = data.get('weight', '01')
            eff = data.get('eff', '00009000900')
            ysz = data.get('ysz', '2')
            fix = data.get('fix', '1')
            dly_interval = data.get('dly_interval', 60)

            if not message:
                raise ValueError("Message is required but not provided")

            command = encode_to_protocol(message, "", color, font, weight, eff, ysz, fix, dly_interval)
            time.sleep(0.1)  # 안정화 대기
            send_command(command)
            logging.info(f"Message displayed successfully: {message}")
            return jsonify({"status": "success", "message": "Emergency message displayed successfully"}), 200

        # 긴급 메시지 해제
        else:
            logging.info("[display] 긴급 모드 해제, 기본 메시지 다시 시작")
            stop_event.clear()  # 중단 이벤트 해제
            # 기존 스레드가 실행 중이면 중복 실행 방지
            if display_thread and display_thread.is_alive():
                logging.info("[display] 기존 display_default_message() 스레드가 실행 중이므로 새로 실행하지 않음")
            else:
                display_thread = threading.Thread(target=display_default_message, daemon=True)
                display_thread.start()
            return jsonify({"status": "success", "message": "Emergency mode deactivated"}), 200

    except ValueError as ve:
        logging.error(f"Validation Error: {ve}")
        return jsonify({"status": "error", "message": str(ve)}), 400

    except TypeError as te:
        logging.error(f"TypeError occurred: {te}")
        return jsonify({"status": "error", "message": "TypeError occurred in display function"}), 400

    except Exception as e:
        logging.error(f"Unexpected Error: {e}")
        return jsonify({"status": "error", "message": "An unexpected error occurred"}), 500

# 서버 종료 및 GPIO 해제
@app.route('/shutdown', methods=['POST'])
def shutdown():
    GPIO.cleanup()
    func = request.environ.get('werkzeug.server.shutdown')
    if func is None:
        raise RuntimeError('Not running with the Werkzeug Server')
    func()
    return 'Server shutting down...'


# WebSocket 연결 상태 왓치독
def ws_watchdog_thread():
    """운영서버 WebSocket 연결 상태를 감시하여 연결 실패 지속 시 프로세스를 재시작합니다."""
    ws_timeout = int(os.getenv("WS_HEALTH_TIMEOUT_SEC", "60"))
    check_interval = int(os.getenv("WS_WATCHDOG_CHECK_INTERVAL_SEC", "30"))
    restart_threshold = int(os.getenv("WS_WATCHDOG_RESTART_THRESHOLD", "10"))
    grace_sec = int(os.getenv("WS_WATCHDOG_GRACE_SEC", "120"))

    start_time = time.monotonic()
    consecutive_failures = 0

    logging.info("ws_watchdog: 시작 timeout=%ss interval=%ss threshold=%s grace=%ss",
                 ws_timeout, check_interval, restart_threshold, grace_sec)

    while True:
        time.sleep(check_interval)

        elapsed = time.monotonic() - start_time
        if elapsed < grace_sec:
            continue

        if is_ws_healthy(ws_timeout):
            if consecutive_failures > 0:
                logging.info("ws_watchdog: WebSocket 연결 복구 확인 (이전 실패 %d회)", consecutive_failures)
            consecutive_failures = 0
        else:
            consecutive_failures += 1
            health = get_ws_health()
            logging.warning("ws_watchdog: WebSocket 연결 실패 감지 %d/%d health=%s",
                           consecutive_failures, restart_threshold, health)

            if consecutive_failures >= restart_threshold:
                logging.critical("ws_watchdog: WebSocket 연결 실패 %d회 연속 - main_ctl 재시작",
                                consecutive_failures)
                try:
                    with open("/home/admin/gunpo/docker/logs/ws_watchdog_restart.log", "a") as f:
                        from datetime import datetime as _dt
                        f.write(f"{_dt.now().isoformat()} RESTART consecutive_failures={consecutive_failures} health={health}\n")
                        f.flush()
                except Exception:
                    pass
                logging.shutdown()
                os._exit(1)

# Flask app 실행
def start_flask_app():
    """Flask 애플리케이션 실행"""
    try:
        logging.info("start_flask_app: Flask 실행")
        app.run(host="0.0.0.0", port=5000, debug=False)
    except Exception as e:
        logging.error(f"start_flask_app: Flask 실행 실패: {e}")
    finally:
        GPIO.cleanup()  # 자원 정리

# stomp client 실행
async def start_stomp_clients():
    await asyncio.gather(
        stomp_client(PROD_WEBSOCKET_URL, "/api/iot/overview"),
    )

# stomp req client 실행
async def start_stomp_req_client():
    await asyncio.gather(
        stomp_req_client(PROD_WEBSOCKET_URL),  # PROD WebSocket URL
    )

if __name__ == "__main__":
    logger = setup_logging("main_ctl")
    # 프로세스 초기화
    flask_process = None
    stomp_process = None
    stomp_req_client_process = None
    display_process = None
    config_fetch_process = None
    fan_control_thread = None
    try:
        config_fetch_thread = threading.Thread(target=start_config_fetch_loop, daemon=True)
        fan_control_thread = threading.Thread(target=start_fan_auto_control, daemon=True)
        ws_watchdog = threading.Thread(target=ws_watchdog_thread, daemon=True)

        # 병렬 프로세스 생성
        flask_process = threading.Thread(target=start_flask_app, daemon=True)
        stomp_process = threading.Thread(target=lambda: asyncio.run(start_stomp_clients()), daemon=True)
        stomp_req_client_process = threading.Thread(target=lambda: asyncio.run(start_stomp_req_client()), daemon=True)
        display_thread = threading.Thread(target=display_default_message, daemon=True)
        thread = threading.Thread(target=start_async_loop, daemon=True)

        # 프로세스 시작
        flask_process.start()
        stomp_process.start()
        stomp_req_client_process.start()
        display_thread.start()
        thread.start()
        config_fetch_thread.start()
        fan_control_thread.start()
        ws_watchdog.start()

        # 메인 프로세스에서 서브 프로세스 대기
        flask_process.join()
        stomp_process.join()
        stomp_req_client_process.join()
        display_thread.join()
        thread.join()
        config_fetch_thread.join()
        fan_control_thread.join()
        ws_watchdog.join()

    except KeyboardInterrupt:
        # 각 프로세스가 초기화되었는지 확인하고 종료
        if flask_process:
            flask_process.terminate()
        if stomp_process:
            stomp_process.terminate()
        if stomp_req_client_process:
            stomp_req_client_process.terminate()

        # 종료된 프로세스 대기
        if flask_process:
            flask_process.join()
        if stomp_process:
            stomp_process.join()
        if stomp_req_client_process:
            stomp_req_client_process.join()
        if config_fetch_process:
            config_fetch_process.terminate()
            config_fetch_process.join()
    finally:
        GPIO.cleanup()  # GPIO 자원 정리
