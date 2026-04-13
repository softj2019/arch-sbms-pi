import asyncio
import os
from dotenv import load_dotenv
from tapo import ApiClient

# 환경 변수 로드
load_dotenv()

async def tapo_auth():
    """Tapo 인증 및 클라이언트 생성"""
    try:
        tapo_username = os.getenv("TAPO_USERNAME")
        tapo_password = os.getenv("TAPO_PASSWORD")
        ip_address = os.getenv("IP_ADDRESS")

        logging.info(f"tapo_auth: TAPO_USERNAME={tapo_username}, IP_ADDRESS={ip_address}")

        if not tapo_username or not tapo_password or not ip_address:
            raise ValueError("환경 변수 TAPO_USERNAME, TAPO_PASSWORD 또는 IP_ADDRESS가 누락되었습니다.")

        client = ApiClient(tapo_username, tapo_password)
        device = await client.p110(ip_address)
        return device
    except Exception as e:
        logging.error(f"tapo_auth: tapo_auth() 오류: {e}")
        raise

# tapo 전원상태 체크
async def check_device_status():
    try:
        device = await tapo_auth()
        logging.info("check_device_status: Tapo 장치 인증 성공. 호출중.")

        info = await device.get_device_info()
        logging.info(f"check_device_status: 장치 정보: {vars(info)}")  # info 객체의 모든 속성을 출력

    except Exception as e:
        logging.error(f"check_device_status: check_device_status() 오류: {e}")

if __name__ == "__main__":
    asyncio.run(check_device_status())
