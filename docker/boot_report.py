#!/usr/bin/env python3
"""
부팅 후 서비스 기동 상태를 STOMP WebSocket으로 운영서버에 전송

cron reboot(03:00) → systemd 자동 실행 → STOMP /api/iot/boot-report 전송
서버 WebSocketController에서 수신 → tb_device_maintenance_log에 기록
"""
import asyncio
import json
import logging
import os
import re
import socket
import subprocess
import time

from dotenv import load_dotenv
from websocket_endpoint import websocket_connection

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("/home/admin/gunpo/docker/logs/boot_report.log", mode="a"),
    ],
)

# 터미널 ID
hostname = socket.gethostname()
match = re.search(r'gunpo-(\d+)', hostname)
TERMINAL_ID = match.group(1) if match else os.getenv('TERMINAL_ID', 'unknown')

SERVICES = ["main_ctl", "cv2_ffmpeg", "air", "gunpo-network-watchdog"]
PROD_WS_URL = os.getenv('PROD_WEBSOCKET_URL', 'ws://175.45.215.53/websocket')


def get_service_status(name):
    try:
        result = subprocess.run(["systemctl", "is-active", name],
                                capture_output=True, text=True, timeout=5)
        return result.stdout.strip()
    except Exception:
        return "unknown"


def get_boot_time():
    try:
        result = subprocess.run(["uptime", "-s"], capture_output=True, text=True, timeout=5)
        return result.stdout.strip()
    except Exception:
        return ""


def get_git_version():
    try:
        result = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                                capture_output=True, text=True, timeout=5,
                                cwd="/home/admin/gunpo")
        return result.stdout.strip()
    except Exception:
        return ""


def collect_report():
    services = {}
    for svc in SERVICES:
        services[svc] = get_service_status(svc)

    # actions-runner
    try:
        result = subprocess.run(
            "systemctl list-units --type=service --state=active | grep actions.runner",
            shell=True, capture_output=True, text=True, timeout=5)
        services["actions-runner"] = "active" if result.stdout.strip() else "inactive"
    except Exception:
        services["actions-runner"] = "unknown"

    all_active = all(v == "active" for k, v in services.items() if k != "actions-runner")

    boot_time = get_boot_time()
    git_ver = get_git_version()
    svc_str = " ".join(f"{k}={v}" for k, v in services.items())

    report = {
        "terminalId": TERMINAL_ID,
        "actionType": "BOOT_REPORT",
        "command": f"cron reboot → boot at {boot_time}",
        "commandResult": f"boot={boot_time} git={git_ver} {svc_str}",
        "executedBy": TERMINAL_ID,
        "status": "SUCCESS" if all_active else "FAILED",
    }
    return report


def create_stomp_connect_frame():
    return "CONNECT\naccept-version:1.1,1.2\nhost:localhost\nlogin:\npasscode:\n\n\x00"


def create_stomp_send_frame(destination, message):
    return f"SEND\ndestination:{destination}\ncontent-length:{len(message)}\n\n{message}\x00"


async def send_report():
    report = collect_report()
    message = json.dumps(report)
    logging.info(f"boot_report: {report['commandResult']}")

    async with websocket_connection(primary_url=PROD_WS_URL, log_context="boot_report") as ws:
        # STOMP CONNECT
        await ws.send(create_stomp_connect_frame())
        resp = await asyncio.wait_for(ws.recv(), timeout=10)
        if "CONNECTED" not in resp:
            logging.error(f"boot_report: STOMP CONNECT 실패: {resp[:50]}")
            return False

        # SEND to /api/iot/boot-report
        frame = create_stomp_send_frame("/api/iot/boot-report", message)
        await ws.send(frame.encode())
        logging.info(f"boot_report: STOMP 전송 완료 terminal={TERMINAL_ID}")
        await asyncio.sleep(1)
        return True


async def main():
    logging.info(f"boot_report: 시작 terminal={TERMINAL_ID}")

    # 서비스 기동 대기 (최대 90초)
    for i in range(18):
        if get_service_status("main_ctl") == "active":
            break
        logging.info(f"boot_report: main_ctl 대기... ({(i+1)*5}초)")
        await asyncio.sleep(5)

    # 추가 안정화 대기
    await asyncio.sleep(10)

    # 전송 (최대 3회 재시도)
    for attempt in range(3):
        try:
            if await send_report():
                logging.info("boot_report: 완료")
                return
        except Exception as e:
            logging.error(f"boot_report: 전송 실패 ({attempt+1}/3): {e}")
        await asyncio.sleep(30)

    logging.error("boot_report: 최종 실패")


if __name__ == "__main__":
    asyncio.run(main())
