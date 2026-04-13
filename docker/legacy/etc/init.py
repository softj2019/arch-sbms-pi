import RPi.GPIO as GPIO
import time

# GPIO 초기화
GPIO.setmode(GPIO.BCM)

# 제어할 핀 번호
PINS = [17, 27, 22]

# 핀 설정: 출력으로 설정하고 초기값을 LOW로 설정
for pin in PINS:
    GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

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
    # 모든 핀을 LOW 상태로 초기화
    for pin in PINS:
        GPIO.output(pin, GPIO.LOW)
    GPIO.cleanup()


def init():
    return None