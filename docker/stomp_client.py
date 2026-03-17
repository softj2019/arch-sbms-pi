from dotenv import load_dotenv
import os
import re
import socket
import asyncio
import websockets
import psutil
import json
import logging
import requests
from tapo_on import get_device_info
import cv2
import urllib.parse

import subprocess
from network_probe import collect_network_status
from network_resilience import (
    NETWORK_OVERVIEW_INTERVAL_SEC,
    NETWORK_RETRY_INTERVAL_SEC,
    build_runtime_fields,
    mark_events_delivered,
    request_reboot,
    should_request_reboot,
    update_network_state,
)
from websocket_endpoint import websocket_connection
from ws_health import report_ws_alive
# .env 파일을 로드
load_dotenv()

# 로깅 설정
logging.basicConfig(
    level=logging.ERROR,
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
API_URL= os.getenv('API_URL')

# RTSP 정보
username = os.getenv("USERNAME_OPENCV")
password = os.getenv("PASSWORD_OPENCV")
camera_ip = os.getenv('IP_OPENCV')
encoded_password = urllib.parse.quote(password)
rtsp_url = f"rtsp://{username}:{encoded_password}@{camera_ip}/stream2"
ip_address_light = os.getenv("IP_ADDRESS_LED")
ip_address_fan = os.getenv("IP_ADDRESS_FAN")
original_str = os.getenv("ORIGINAL_STR")

# RTSP 스트림 연결
cap = cv2.VideoCapture(rtsp_url)
if cap.isOpened():
    cv_power="ON"
else:
    cv_power="OFF"

# stomp connect frame 생성
def create_stomp_connect_frame():
    frame = "CONNECT\n"
    frame += "accept-version:1.1,1.2\n"
    frame += "host:localhost\n"
    frame += "login:\n"
    frame += "passcode:\n\n"
    frame += "\x00"
    return frame

# stomp subscribe frame 생성
def create_stomp_subscribe_frame(destination, subscription_id):
    frame = f"SUBSCRIBE\ndestination:{destination}\nid:{subscription_id}\nack:auto\n\n\x00"
    return frame

# stomp send frame 생성
def create_stomp_send_frame(destination, message):
    frame = f"SEND\ndestination:{destination}\ncontent-length:{len(message)}\n\n{message}\x00"
    return frame

# 라즈베리파이 보드의 외부 Ip 주소 반환
async def get_ip_address():
    status = await asyncio.to_thread(collect_network_status)
    return status.public_ip or "127.0.0.1"

# 시리얼 포트상태를 서버에서 가져오기
async def get_serial_status():
    try:
        response = requests.get(f"{API_URL}/serial_status", timeout=3)
        response.raise_for_status()  # HTTP 오류 발생 시 예외 처리
        data = response.json()
        return data.get("serial_status", "OFF")
    except requests.RequestException as e:
        logging.error(f"Error fetching serial status: {e}")
        return "OFF"

async def get_screen_status():
    try:
        response = requests.get(f"{API_URL}/screen_status", timeout=3)
        response.raise_for_status()
        data = response.json()
        return data.get("screen_status", {})
    except requests.RequestException as e:
        logging.error(f"Error fetching screen status: {e}")
        return {}

# 비동기 ping 테스트로 장치 응답여부 확인
async def ping_device(ip):
    try:
        process = await asyncio.create_subprocess_exec(
            "ping", "-c", "1", "-W", "1", ip,  # Linux, macOS용
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )
        return await process.wait() == 0  # 0이면 성공, 1이면 실패
    except Exception as e:
        logging.error(f"Ping test failed for {ip}: {e}")
        return False
    
# tapo 팬장치 상태 확인
async def get_fan_info():
    try:
        if not await ping_device(ip_address_fan):
            logging.warning(f"get_fan_info: ping 통신 실패: ({ip_address_fan}")
            return "OFF"

        device_info = await get_device_info(ip_address_fan)
        logging.warning(f"get_fan_info: 팬 상태: {device_info.model_dump()}")

        return "ON" if device_info.device_on else "OFF"
    except Exception as e:
        logging.error(f"get_fan_info: 팬 상태 조회 실패({ip_address_fan}): {e}")
        return "OFF"

# tapo 조명장치 상태 확인
async def get_light_info():
    try:
        if not await ping_device(ip_address_light):
            logging.warning(f"get_light_info: ping 통신 실패: ({ip_address_light}")
            return "OFF"

        device_info = await get_device_info(ip_address_light)
        logging.warning(f"get_light_info: 조명 상태: {device_info.model_dump()}")

        return "ON" if device_info.device_on else "OFF"
    except Exception as e:
        logging.error(f"get_light_info: 조명 상태 조회 실패({ip_address_light}): {e}")
        return "OFF"

# HDMI A-1, A-2 의 전원 상태 확인
async def get_hdmi_status():
    try:
        # 환경 변수 설정 (Wayland 환경 대응)
        os.environ["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"

        # wlr-randr 실행
        result = subprocess.run(["wlr-randr"], capture_output=True, text=True)
        output = result.stdout.strip() or result.stderr.strip()  # stderr도 확인

        # HDMI-A-1 및 HDMI-A-2 상태 확인
        hdmi1_on = "HDMI-A-1" in output and "Enabled: yes" in output
        hdmi2_on = "HDMI-A-2" in output and "Enabled: yes" in output

        # 둘 중 하나라도 ON이면 "ON" 반환, 아니면 "OFF"
        return "ON" if hdmi1_on or hdmi2_on else "OFF"
    except Exception as e:
        logging.error(f"get_hdmi_status: 전원상태 확인 실패: {e}")
        return "ERROR"

# 시스템정보수집
async def collect_system_info():
    cpu_usage = psutil.cpu_percent(interval=1)
    memory = psutil.virtual_memory()
    total_memory = memory.total / (1024**3)
    used_memory = (memory.total - memory.available) / (1024**3)
    available_memory = memory.available / (1024**3)
    disk = psutil.disk_usage('/')
    total_disk = disk.total / (1024**3)
    used_disk = (disk.total - disk.free) / (1024**3)
    available_disk = disk.free / (1024**3)
    network_status = await asyncio.to_thread(collect_network_status)
    # serial_status = await get_serial_status()
    fan_info = await get_fan_info()  # `await` 추가
    light_info = await get_light_info()  # `await` 추가
    hdmi_status = await get_hdmi_status()
    # CPU 온도 수집
    try:
        with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
            cpu_temp = float(f.readline().strip()) / 1000.0  # 온도를 섭씨로 변환
    except FileNotFoundError:
        cpu_temp = None  # 파일이 없을 경우 None으로 설정

    data = {
        "terminal_id": TERMINAL_ID,
        "ipaddress": network_status.router_wan_ip or network_status.public_ip or "127.0.0.1",
        "rfc_cpu": f"{cpu_usage:.2f}",
        "cpu_temperature": f"{cpu_temp:.2f}" if cpu_temp is not None else "N/A",
        "rfc_memory_total": f"{total_memory:.2f}",
        "rfc_memory_used": f"{used_memory:.2f}",
        "rfc_memory_available": f"{available_memory:.2f}",
        "rfc_storage_total": f"{total_disk:.2f}",
        "rfc_storage_used": f"{used_disk:.2f}",
        "rfc_storage_available": f"{available_disk:.2f}",
        "ctl_board_power": "ON",
        "smartscreen_power":"ON",
        "led_panel_power": "ON",
        "led_light_power": light_info,
        "lcd_display_power": hdmi_status,
        "lte_router_power": "ON",
        "lte_router_gateway": network_status.router_gateway or "",
        "lte_router_gateway_status": "ON" if network_status.router_gateway_ok else "OFF",
        "lte_router_link": "ON" if network_status.lte_router_connected else "OFF",
        "lte_router_wan_ip": network_status.router_wan_ip or "",
        "vc_power": cv_power,
        "fan": fan_info,
        "network_outbound": "ON" if network_status.outbound_ok else "OFF",
        "network_health": "ON" if network_status.healthy else "OFF",
        "network_check_required": "Y" if not network_status.healthy else "N",
    }
    data.update(build_runtime_fields(network_status, include_pending_events=True))
    return data

# STOMP 클라이언트
async def stomp_client(url, destination):
    while True:
        try:
            network_status = await asyncio.to_thread(collect_network_status)
            state = await asyncio.to_thread(update_network_state, network_status, "stomp_client")
            if not network_status.healthy:
                logging.error(
                    "stomp_client: WAN/외부송신 장애로 overview 전송 보류 (%s/%s) reason=%s",
                    state["consecutive_failures"],
                    os.getenv("NETWORK_FAILURE_REBOOT_THRESHOLD", "10"),
                    network_status.failure_reason or "",
                )
                if should_request_reboot(state):
                    await asyncio.to_thread(
                        request_reboot,
                        network_status.failure_reason or "network_unhealthy",
                        "stomp_client",
                    )
                await asyncio.sleep(NETWORK_RETRY_INTERVAL_SEC)
                continue

            async with websocket_connection(primary_url=url, log_context="stomp_client") as websocket:
                # 1. STOMP CONNECT 프레임 전송
                connect_frame = create_stomp_connect_frame()
                await websocket.send(connect_frame)

                # 2. STOMP SUBSCRIBE 프레임 전송
                subscribe_frame = create_stomp_subscribe_frame(destination=destination, subscription_id="1")
                await websocket.send(subscribe_frame)

                # 3. 주기적으로 데이터 전송
                while True:
                    network_status = await asyncio.to_thread(collect_network_status)
                    state = await asyncio.to_thread(update_network_state, network_status, "stomp_client")
                    if not network_status.healthy:
                        logging.error(
                            "stomp_client: overview 전송 중단. %s초 후 재시도 (%s/%s) reason=%s",
                            NETWORK_RETRY_INTERVAL_SEC,
                            state["consecutive_failures"],
                            os.getenv("NETWORK_FAILURE_REBOOT_THRESHOLD", "10"),
                            network_status.failure_reason or "",
                        )
                        if should_request_reboot(state):
                            await asyncio.to_thread(
                                request_reboot,
                                network_status.failure_reason or "network_unhealthy",
                                "stomp_client",
                            )
                        await asyncio.sleep(NETWORK_RETRY_INTERVAL_SEC)
                        break

                    system_info = await collect_system_info()  # `await` 추가
                    message = json.dumps(system_info)  # ✅ JSON 변환 오류 해결
                    send_frame = create_stomp_send_frame(destination=destination, message=message)
                    await websocket.send(send_frame.encode())
                    report_ws_alive("stomp_client")
                    await asyncio.to_thread(mark_events_delivered)
                    await asyncio.sleep(NETWORK_OVERVIEW_INTERVAL_SEC)
        except (websockets.ConnectionClosedError, websockets.ConnectionClosedOK, ConnectionRefusedError) as e:
            logging.error(f"stomp_client: 소켓통신 실패({url}): {e}")
            await asyncio.sleep(NETWORK_RETRY_INTERVAL_SEC)
        except Exception as e:
            logging.error(f"Unexpected error in WebSocket connection at {url}: {e}")
            await asyncio.sleep(NETWORK_RETRY_INTERVAL_SEC)
