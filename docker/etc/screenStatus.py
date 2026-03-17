import RPi.GPIO as GPIO
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
# GPIO 핀 정의 (모터의 상태를 나타내는 핀 번호)
UP_PIN = 17    # UP 동작 핀
DOWN_PIN = 27  # DOWN 동작 핀
STOP_PIN = 22  # STOP 상태 핀
def initialize_gpio():
    """
    GPIO 초기화 함수
    """
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(UP_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.setup(DOWN_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.setup(STOP_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    logging.info("GPIO initialized.")

def get_motor_status():
    """
    RTS485 모터 상태를 확인하여 'U', 'D', 'S' 중 하나를 반환합니다.
    :return: 'U' (Up), 'D' (Down), 'S' (Stop) 문자열
    """
    try:
        # GPIO 핀 상태 확인
        up_state = GPIO.input(UP_PIN)
        down_state = GPIO.input(DOWN_PIN)
        stop_state = GPIO.input(STOP_PIN)
        logging.info(f"Motor states: UP={up_state}, DOWN={down_state}, STOP={stop_state}")
        # 상태 판별
        if up_state == GPIO.HIGH:
            logging.info("Motor is moving UP")
            return "U"
        elif down_state == GPIO.HIGH:
            logging.info("Motor is moving DOWN")
            return "D"
        elif stop_state == GPIO.HIGH:
            logging.info("Motor is STOPPED")
            return "S"
        else:
            logging.warning("Motor status is UNKNOWN")
            return "UNKNOWN"  # 예외적으로 모든 핀이 LOW 상태일 경우
    except Exception as e:
        logging.error(f"Error getting motor status: {e}")
        return "ERROR"

if __name__ == "__main__":
    # initialize_gpio()
    # 모터 상태 확인
    motor_status = get_motor_status()
    print(f"Motor Status: {motor_status}")
