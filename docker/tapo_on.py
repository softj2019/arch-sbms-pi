import asyncio
import os
from dotenv import load_dotenv
from tapo import ApiClient
import logging
import json
from typing import Optional
from pydantic import BaseModel
import time
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

# tapo 테스트
async def tapo_test(ip):
    username = os.getenv("TAPO_USERNAME")
    password = os.getenv("TAPO_PASSWORD")

    logging.info(f"TAPO_USERNAME: {username}")
    logging.info(f"TAPO_PASSWORD: {password}")

    client = ApiClient(username, password)

    # 1) P110 객체 생성 테스트
    try:
        logging.info("p110 객체 생성 시도")
        device = await client.p110(ip)
        logging.info("p110 객체 생성 성공")
    except Exception as e:
        logging.info(f"p110 생성 실패: {e}")
        return

    # 2) 기본 장치 정보 조회 (P110이 지원하는 공식 API)
    try:
        info = await device.get_device_info()
        logging.info("device_info 응답:")
        logging.info(info)
    except Exception as e:
        logging.info(f"get_device_info 오류: {e}")

    # 3) 에너지 사용량 조회 (P110 전용 API)
    try:
        energy = await device.get_energy_usage()
        logging.info("energy_usage 응답:")
        logging.info(energy)
    except Exception as e:
        logging.info(f"get_energy_usage 오류: {e}")

# tapo 계정 인증
async def tapo_auth(ip):
    # Tapo 인증을 수행하고 P110 장치 인스턴스를 반환
    tapo_username = os.getenv("TAPO_USERNAME")
    tapo_password = os.getenv("TAPO_PASSWORD")

    client = ApiClient(tapo_username, tapo_password)
    return await client.p110(ip)

# tapo 정보 조회
async def get_device_info(ip):
    try:
        # tapo 테스트부터 실행 (평소에는 주석처리해야함)
        # await tapo_test(ip)

        # 계정인증
        device = await tapo_auth(ip)

        # JSON 원본 가져오기 (모든 필드 포함되지 않아도 오류 안남)
        raw = await device.get_device_info_json()

        # 로깅 확인
        logging.debug(f"get_device_info: raw json: {json.dumps(raw, indent=2)}")

        # 안전하게 dict -> 모델 변환
        device_on = raw.get("device_on", False)
        overheat = raw.get("overheat_status") if "overheat_status" in raw else None

        info = DeviceInfo(device_on=device_on, overheat_status=overheat)
        return info

    except Exception as e:
        if ip.endswith("103"):
            device_name = "LED"
        elif ip.endswith("104"):
            device_name = "FAN"
        logging.error(f"get_device_info: {device_name} 통신 실패: {e}")
        time.sleep(10)

        return DeviceInfo(device_on=False)

# tapo 전원 on
async def device_on(ip):
    device = await tapo_auth(ip)
    await device.on()

    dev_name = "LED" if ip.endswith("103") else "FAN"
    logging.info(f"device_on: {dev_name}")

# tapo 전원 off
async def device_off(ip):
    device = await tapo_auth(ip)
    await device.off()

    dev_name = "LED" if ip.endswith("103") else "FAN"
    logging.info(f"device_off: {dev_name}")

if __name__ == "__main__":
    logger = setup_logging("tapo")
    async def main():
        info = await get_device_info("192.168.10.103")
        # dict로 변환 후 json.dumps 사용
        logging.info("TAPO 장치 상태 정보:\n%s", json.dumps(info.model_dump(), indent=2, ensure_ascii=False))

    asyncio.run(main())