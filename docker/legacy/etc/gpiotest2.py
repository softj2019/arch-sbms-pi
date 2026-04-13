import RPi.GPIO as GPIO
import time

TEST_PIN = 17  # 테스트할 핀 번호
GPIO.setmode(GPIO.BCM)

# 1. 입력 모드로 설정 후 테스트
GPIO.setup(TEST_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
print("GPIO를 입력(PULL_DOWN) 모드로 설정함. 저항 및 전압 다시 측정 요망.")
time.sleep(5)

# 2. 출력 모드로 설정 후 테스트
GPIO.setup(TEST_PIN, GPIO.OUT)
GPIO.output(TEST_PIN, GPIO.HIGH)
print("GPIO를 출력 HIGH 모드로 설정함. 저항 및 전압 다시 측정 요망.")
time.sleep(5)

GPIO.output(TEST_PIN, GPIO.LOW)
print("GPIO를 출력 LOW 모드로 설정함. 저항 및 전압 다시 측정 요망.")
time.sleep(5)

GPIO.cleanup()
