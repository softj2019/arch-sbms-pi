import RPi.GPIO as GPIO
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
# GPIO 핀 설정 (모터라인 수신기와 연결된 핀 번호)
MOTOR_POWER_PIN = 17  # 예: GPIO 17 핀이 전원 상태를 감지하도록 연결


def initialize_gpio():
    """GPIO 초기화 함수"""
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(MOTOR_POWER_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)  # 풀다운 저항 사용


def get_motor_power_status():
    """
    모터라인 수신기의 전원 상태 확인 함수
    :return: 'ON' 또는 'OFF' 문자열 반환
    """
    try:
        # GPIO 핀의 현재 상태 읽기
        power_state = GPIO.input(MOTOR_POWER_PIN)

        # 전원 상태 반환
        if power_state == GPIO.HIGH:
            logging.info("Motor power is ON")
            return "ON"
        else:
            logging.info("Motor power is OFF")
            return "OFF"
    except Exception as e:
        logging.error(f"Error reading motor power status: {e}")
        return "ERROR"


if __name__ == "__main__":
    # GPIO 초기화
    initialize_gpio()

    # 전원 상태 확인
    motor_status = get_motor_power_status()
