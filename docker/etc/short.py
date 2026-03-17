import RPi.GPIO as GPIO
import time

TEST_PIN = 17  # 테스트할 핀
ALTERNATE_PIN = 27  # 비교할 다른 핀

GPIO.setmode(GPIO.BCM)
GPIO.setup(TEST_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

if GPIO.input(TEST_PIN) == GPIO.HIGH:
    print("GPIO가 항상 HIGH 상태 -> 쇼트 가능성 있음")
elif GPIO.input(TEST_PIN) == GPIO.LOW:
    print("GPIO가 항상 LOW 상태 -> 쇼트 가능성 있음")
else:
    print("GPIO 동작 정상")
