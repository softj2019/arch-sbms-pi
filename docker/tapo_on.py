import asyncio
import os
from dotenv import load_dotenv
import logging
import json
from typing import Optional
from pydantic import BaseModel
import time
from kasa import Discover
from logging_handler import setup_logging

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)

class DeviceInfo(BaseModel):
    device_on: bool
    overheat_status: Optional[bool] = None


def _dev_name(ip: str) -> str:
    if ip.endswith("103"):
        return "LED"
    elif ip.endswith("104"):
        return "FAN"
    return ip


async def _connect(ip: str):
    """python-kasa 로 Tapo P110 에 연결 (로컬 KLAP v2, 포트 80)"""
    username = os.getenv("TAPO_USERNAME")
    password = os.getenv("TAPO_PASSWORD")
    return await Discover.discover_single(ip, username=username, password=password, timeout=10)


# tapo 정보 조회
async def get_device_info(ip: str) -> DeviceInfo:
    try:
        dev = await _connect(ip)
        device_on = dev.is_on
        return DeviceInfo(device_on=device_on)
    except Exception as e:
        logging.error(f"get_device_info: {_dev_name(ip)} 통신 실패: {e}")
        time.sleep(10)
        return DeviceInfo(device_on=False)


# tapo 전원 on
async def device_on(ip: str) -> None:
    try:
        dev = await _connect(ip)
        await dev.turn_on()
        logging.info(f"device_on: {_dev_name(ip)}")
    except Exception as e:
        logging.error(f"device_on: {_dev_name(ip)} 실패: {e}")


# tapo 전원 off
async def device_off(ip: str) -> None:
    try:
        dev = await _connect(ip)
        await dev.turn_off()
        logging.info(f"device_off: {_dev_name(ip)}")
    except Exception as e:
        logging.error(f"device_off: {_dev_name(ip)} 실패: {e}")


if __name__ == "__main__":
    logger = setup_logging("tapo")

    async def main():
        info = await get_device_info("192.168.10.103")
        logging.info("TAPO 장치 상태 정보:\n%s", json.dumps(info.model_dump(), indent=2, ensure_ascii=False))

    asyncio.run(main())
