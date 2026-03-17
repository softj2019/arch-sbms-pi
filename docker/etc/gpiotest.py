import RPi.GPIO as GPIO
import time

TEST_PINS = [26, 20, 21]  # 사용할 릴레이 제어 핀 (RPi Relay Board 기본값)

GPIO.setmode(GPIO.BCM)

# 모든 핀을 출력 모드로 설정
for pin in TEST_PINS:
    GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)
    print(f"✅ GPIO {pin} 설정 완료")

try:
    while True:
        for pin in TEST_PINS:
            # 개별 릴레이 활성화
            print(f"🔵 GPIO {pin} 릴레이 ON (HIGH)")
            GPIO.output(pin, GPIO.HIGH)
            time.sleep(1)  # 릴레이 상태 유지 (3초)

            # 릴레이 비활성화
            print(f"⚫ GPIO {pin} 릴레이 OFF (LOW)")
            GPIO.output(pin, GPIO.LOW)
            time.sleep(2)  # 다음 릴레이 진행 전 2초 대기

except KeyboardInterrupt:
    pass
finally:
    GPIO.cleanup()
    print("✅ GPIO 핀 정리 완료. 테스트 종료")
