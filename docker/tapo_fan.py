import asyncio
import os
from dotenv import load_dotenv
from tapo import ApiClient

load_dotenv()

async def tapo_auth():
    """Tapo 인증을 수행하고 P110 장치 인스턴스를 반환"""
    tapo_username = os.getenv("TAPO_USERNAME")
    tapo_password = os.getenv("TAPO_PASSWORD")
    ip_address = os.getenv("IP_ADDRESS_FAN")

    client = ApiClient(tapo_username, tapo_password)
    return await client.p110(ip_address)

async def get_device_info():
    """장치 정보 가져오기"""
    device = await tapo_auth()
    return await device.get_device_info()

async def device_on():
    """기기 전원을 ON"""
    device = await tapo_auth()
    await device.on()
    print("장치 전원을 켰습니다.")

async def device_off():
    """기기 전원을 OFF"""
    device = await tapo_auth()
    await device.off()
    print("장치 전원을 껐습니다.")

async def toggle_device():
    """현재 전원 상태를 확인 후 자동으로 ON/OFF 토글"""
    device = await tapo_auth()
    info = await device.get_device_info()

    # 객체 속성 접근 방식 사용
    if info.device_on:
        await device.off()
        print("전원이 켜져 있어서 끕니다.")
    else:
        await device.on()
        print("전원이 꺼져 있어서 켭니다.")

if __name__ == "__main__":
    asyncio.run(toggle_device())
