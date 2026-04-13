import serial
import logging
import time

# 로깅 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# 시리얼 포트 설정
SERIAL_PORT = "/dev/ttyUSB0"  # USB to RS232 포트
BAUD_RATE = 115200  # 전광판 통신 속도
TIMEOUT = 0.5  # 응답 대기 시간

# 테스트 명령어 (간단한 상태 확인용 명령어)
TEST_CMD = bytes.fromhex("02 84 08 00 49 00 44 00 58 00 3D 00 39 00 39 00 D5 03")  # 메시지 삭제 명령 (전광판 응답 확인용)

def check_led_power_status():
    """전광판 전원이 켜져 있는지 확인"""
    try:
        with serial.Serial(SERIAL_PORT, baudrate=BAUD_RATE, timeout=TIMEOUT) as ser:
            logging.info("✅ 시리얼 포트 연결됨, 전광판 상태 확인 중...")

            # 테스트 명령어 전송
            ser.write(TEST_CMD)
            time.sleep(0.2)  # 응답 대기
            response = ser.read(10)  # 응답 데이터 읽기

            if response:
                logging.info(f"🔄 응답 데이터: {response.hex()}")
                print("🔋 LED 전광판 전원 상태: ON (전원이 켜져 있음)")
                return "ON"
            else:
                print("🔌 LED 전광판 전원 상태: OFF (전원이 꺼져 있음)")
                return "OFF"

    except serial.SerialException as e:
        logging.error(f"❌ 시리얼 통신 오류: {e}")
        return "ERROR"

# 실행
if __name__ == "__main__":
    status = check_led_power_status()
    print(f"📢 최종 판별된 전광판 상태: {status}")
