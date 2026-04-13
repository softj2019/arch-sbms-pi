import RPi.GPIO as GPIO
import time

# GPIO 초기화
GPIO.setmode(GPIO.BCM)

# 확인할 핀 번호
PINS = [17, 27, 22]

# 핀 설정: 입력으로 설정하고 풀다운 저항 설정
for pin in PINS:
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

# 핀 상태 확인 함수
def check_pin_states(pins):
    for pin in pins:
        state = GPIO.input(pin)
        status = "HIGH" if state == GPIO.HIGH else "LOW"
        print(f"Pin {pin} is {status}")

try:
    # check_pin_states(PINS)
    while True:
        check_pin_states(PINS)
        time.sleep(1)  # 1초마다 상태 확인
except KeyboardInterrupt:
    print("\nExit program.")
finally:
    GPIO.cleanup()


def gpio_status():
    return None