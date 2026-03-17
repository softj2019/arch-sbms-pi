import RPi.GPIO as GPIO
import time

# 사용할 GPIO 핀 번호 (BCM 모드 기준)
LED_PIN = 18

# GPIO 설정
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(LED_PIN, GPIO.OUT)

# LED ON
print("LED ON")
GPIO.output(LED_PIN, GPIO.HIGH)
# time.sleep(5)  # 5초 동안 켜짐

# LED OFF
# print("LED OFF")
# GPIO.output(LED_PIN, GPIO.LOW)

# GPIO 정리
GPIO.cleanup()
