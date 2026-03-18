#!/usr/bin/env python3
"""
일일 헬스체크 리포트 - 매일 06:00 cron 실행
각 Pi에서 자체 상태를 수집하여 STOMP으로 운영서버에 전송

수집 항목:
- 서비스 상태 (main_ctl, cv2_ffmpeg, air, watchdog, actions-runner)
- 디스크/메모리 사용률
- 최근 24시간 에러 카운트
- STOMP 연결 성공률
- LED 전광판 동작 상태
- NTP 동기화 상태
- Git 버전
- 부팅 시간/Uptime
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
        logging.FileHandler("/home/admin/gunpo/docker/logs/daily_health.log", mode="a"),
    ],
)

hostname = socket.gethostname()
match = re.search(r'gunpo-(\d+)', hostname)
TERMINAL_ID = match.group(1) if match else os.getenv('TERMINAL_ID', 'unknown')
PROD_WS_URL = os.getenv('PROD_WEBSOCKET_URL', 'ws://175.45.215.53/websocket')


def run_cmd(cmd, timeout=10):
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return result.stdout.strip()
    except Exception:
        return ""


def get_service_status(name):
    return run_cmd(f"systemctl is-active {name}")


def get_disk_usage():
    try:
        out = run_cmd("df -h / | tail -1")
        parts = out.split()
        return {"total": parts[1], "used": parts[2], "avail": parts[3], "percent": parts[4]}
    except Exception:
        return {}


def get_memory_usage():
    try:
        out = run_cmd("free -m | grep Mem")
        parts = out.split()
        total = int(parts[1])
        used = int(parts[2])
        return {"total_mb": total, "used_mb": used, "percent": f"{used*100//total}%"}
    except Exception:
        return {}


def count_errors_24h():
    """최근 24시간 에러 카운트"""
    counts = {}
    log_files = {
        "app.err": "/home/admin/gunpo/docker/logs/app.err",
        "cv2_ffmpeg": "/home/admin/gunpo/docker/logs/cv2_ffmpeg.log",
    }
    for name, path in log_files.items():
        try:
            # 오늘 날짜 기준
            today = time.strftime("%Y-%m-%d")
            count = run_cmd(f"grep -c '{today}.*ERROR' {path} 2>/dev/null || echo 0")
            counts[name] = int(count)
        except Exception:
            counts[name] = -1

    # STOMP 에러 (message too big)
    counts["stomp_1009"] = int(run_cmd(
        f"grep -c '1009.*message too big' /home/admin/gunpo/docker/logs/app.err 2>/dev/null || echo 0"
    ) or 0)

    # WebSocket 끊김
    counts["ws_disconnect"] = int(run_cmd(
        f"grep -c 'going away' /home/admin/gunpo/docker/logs/app.err 2>/dev/null || echo 0"
    ) or 0)

    # LED 통신 에러
    counts["led_error"] = int(run_cmd(
        f"grep -c 'LED.*실패\\|Deleting message' /home/admin/gunpo/docker/logs/app.log 2>/dev/null || echo 0"
    ) or 0)

    # Tapo 통신 에러
    counts["tapo_error"] = int(run_cmd(
        f"grep -c 'Tapo\\|tapo.*실패\\|FAN 통신' /home/admin/gunpo/docker/logs/app.err 2>/dev/null || echo 0"
    ) or 0)

    return counts


def get_led_status():
    """LED 전광판 최근 동작 확인"""
    last = run_cmd("grep '메시지 갱신' /home/admin/gunpo/docker/logs/app.log 2>/dev/null | tail -1 | grep -oP '갱신: \\K[0-9:]+'")
    return last or "N/A"


def get_ntp_status():
    return run_cmd("timedatectl show --property=NTPSynchronized --value 2>/dev/null") or "unknown"


def get_network_health():
    """네트워크 상태"""
    healthy = run_cmd("grep 'healthy=Y' /home/admin/gunpo/docker/logs/app.log 2>/dev/null | tail -1")
    return "healthy" if "healthy=Y" in healthy else "unhealthy"


def collect_daily_report():
    services = {
        "main_ctl": get_service_status("main_ctl"),
        "cv2_ffmpeg": get_service_status("cv2_ffmpeg"),
        "air": get_service_status("air"),
        "watchdog": get_service_status("gunpo-network-watchdog"),
        "runner": get_service_status("actions.runner.*"),
    }

    # runner 상태 보정
    if services["runner"] != "active":
        runner_check = run_cmd("systemctl list-units --type=service --state=active | grep -c actions.runner")
        services["runner"] = "active" if int(runner_check or 0) > 0 else "inactive"

    errors = count_errors_24h()
    disk = get_disk_usage()
    memory = get_memory_usage()

    all_svc_ok = all(v == "active" for k, v in services.items())
    disk_warn = int(disk.get("percent", "0%").replace("%", "")) > 80 if disk.get("percent") else False
    mem_warn = int(memory.get("percent", "0%").replace("%", "")) > 80 if memory.get("percent") else False
    high_errors = errors.get("app.err", 0) > 100

    # 종합 판정
    if not all_svc_ok:
        health = "CRITICAL"
    elif disk_warn or mem_warn or high_errors:
        health = "WARNING"
    else:
        health = "OK"

    report = {
        "terminalId": TERMINAL_ID,
        "actionType": "DAILY_HEALTH",
        "command": f"daily health check {time.strftime('%Y-%m-%d %H:%M')}",
        "executedBy": TERMINAL_ID,
        "status": "SUCCESS" if health == "OK" else "FAILED",
        "commandResult": json.dumps({
            "health": health,
            "services": services,
            "disk": disk,
            "memory": memory,
            "errors_24h": errors,
            "led_last": get_led_status(),
            "ntp": get_ntp_status(),
            "network": get_network_health(),
            "git": run_cmd("cd /home/admin/gunpo && git log --oneline -1 | cut -c1-7"),
            "uptime": run_cmd("uptime -p"),
            "boot_time": run_cmd("uptime -s"),
        }, ensure_ascii=False),
    }
    return report


def create_stomp_connect_frame():
    return "CONNECT\naccept-version:1.1,1.2\nhost:localhost\nlogin:\npasscode:\n\n\x00"


def create_stomp_send_frame(destination, message):
    return f"SEND\ndestination:{destination}\ncontent-length:{len(message)}\n\n{message}\x00"


async def send_report():
    report = collect_daily_report()
    logging.info(f"daily_health: terminal={TERMINAL_ID} health={json.loads(report['commandResult'])['health']}")

    message = json.dumps(report, ensure_ascii=False)

    async with websocket_connection(primary_url=PROD_WS_URL, log_context="daily_health") as ws:
        await ws.send(create_stomp_connect_frame())
        resp = await asyncio.wait_for(ws.recv(), timeout=10)
        if "CONNECTED" not in resp:
            logging.error(f"daily_health: STOMP CONNECT 실패")
            return False

        frame = create_stomp_send_frame("/api/iot/boot-report", message)
        await ws.send(frame.encode())
        logging.info(f"daily_health: 전송 완료")
        await asyncio.sleep(1)
        return True


async def main():
    logging.info(f"daily_health: 시작 terminal={TERMINAL_ID}")

    for attempt in range(3):
        try:
            if await send_report():
                logging.info("daily_health: 완료")
                return
        except Exception as e:
            logging.error(f"daily_health: 전송 실패 ({attempt+1}/3): {e}")
        await asyncio.sleep(30)

    logging.error("daily_health: 최종 실패")


if __name__ == "__main__":
    main() if asyncio.get_event_loop().is_running() else asyncio.run(main())
