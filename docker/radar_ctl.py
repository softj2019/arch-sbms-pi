#!/usr/bin/env python3
"""RCWL-0516 레이더 단독 감지 → API POST / LED 릴레이 재실 제어"""
import os, sys, time, logging, requests, threading
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger         = logging.getLogger("RadarCtl")
detect_logger  = logging.getLogger("RadarCtl.detect")
led_logger     = logging.getLogger("RadarCtl.led")

class _SuppressRelayBoard(logging.Filter):
    def filter(self, record):
        return "relay_board" not in record.getMessage()

logging.getLogger().addFilter(_SuppressRelayBoard())

RADAR_PIN         = int(os.getenv("RADAR_GPIO_PIN", "4"))
RADAR_HOLDTIME    = float(os.getenv("RADAR_HOLDTIME", "3.0"))
API_URL           = os.getenv("API_URL", "http://localhost:5000")
RADAR_ENABLED     = os.getenv("RADAR_ENABLED", "true").lower() == "true"
SKIP_SENDS        = os.getenv("SKIP_SENDS", "false").lower() == "true"
RADAR_MODE        = os.getenv("RADAR_MODE", "post")
PRESENCE_LED_PIN  = int(os.getenv("PRESENCE_LED_PIN", "20"))
PRESENCE_DURATION = float(os.getenv("PRESENCE_DURATION", "7.0"))

import RPi.GPIO as GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(RADAR_PIN, GPIO.IN)

sys.path.insert(0, os.path.dirname(__file__))
from devices.relay_board import relay_on, relay_off


def post_radar(active: bool):
    if SKIP_SENDS or not RADAR_ENABLED:
        logger.info(f"[SKIP] radar active={active}")
        return
    def _send():
        count = 1 if active else 0
        for attempt in range(3):
            try:
                requests.post(f"{API_URL}/update_count",
                              json={"count": count, "source": "radar"},
                              timeout=10)
                logger.info(f"[POST] update_count count={count}")
                return
            except Exception as e:
                if attempt < 2:
                    logger.warning(f"POST 재시도 {attempt+1}/2: {e}")
                    time.sleep(0.5)
                else:
                    logger.warning(f"POST 실패: {e}")
    threading.Thread(target=_send, daemon=True).start()


def run_post_mode():
    logger.info(f"[POST 모드] 감지 시작 (GPIO{RADAR_PIN})")
    prev = GPIO.input(RADAR_PIN)
    last_active_ts = 0.0
    try:
        while True:
            v = GPIO.input(RADAR_PIN)
            now = time.time()
            if v == 1 and prev == 0:
                last_active_ts = now
                detect_logger.info(f"[DETECT] ON  GPIO{RADAR_PIN}")
                post_radar(True)
            elif v == 0 and last_active_ts > 0 and (now - last_active_ts) > RADAR_HOLDTIME:
                last_active_ts = 0.0
                detect_logger.info(f"[DETECT] OFF GPIO{RADAR_PIN}")
                post_radar(False)
            prev = v
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        GPIO.cleanup()


def run_presence_led_mode():
    relay_off(PRESENCE_LED_PIN)
    logger.info(f"[재실 LED 모드] 감지=GPIO{RADAR_PIN}, LED=GPIO{PRESENCE_LED_PIN}, 듀레이션={PRESENCE_DURATION}s")

    led_on = False
    led_off_time = 0.0
    prev_v = GPIO.input(RADAR_PIN)

    try:
        while True:
            v = GPIO.input(RADAR_PIN)
            now = time.time()

            if led_on:
                if v == 1 and prev_v == 0:  # 상승 에지에서만 연장 로그
                    led_off_time = now + PRESENCE_DURATION
                    detect_logger.info(f"[DETECT] ON  GPIO{RADAR_PIN} → 타이머 연장 ({PRESENCE_DURATION}s)")
                elif v == 1:
                    led_off_time = now + PRESENCE_DURATION  # 연장은 계속 적용
                if now >= led_off_time:
                    relay_off(PRESENCE_LED_PIN)
                    led_on = False
                    led_logger.info(f"[LED] OFF  GPIO{PRESENCE_LED_PIN} (듀레이션 만료)")

            else:
                if v == 1:
                    relay_on(PRESENCE_LED_PIN)
                    led_on = True
                    led_off_time = now + PRESENCE_DURATION
                    detect_logger.info(f"[DETECT] ON  GPIO{RADAR_PIN}")
                    led_logger.info(f"[LED] ON   GPIO{PRESENCE_LED_PIN} ({PRESENCE_DURATION}s 후 OFF)")

            prev_v = v
            time.sleep(0.05)

    except KeyboardInterrupt:
        relay_off(PRESENCE_LED_PIN)
        logger.info("종료")
    finally:
        GPIO.cleanup()


def main():
    if not RADAR_ENABLED:
        logger.info("RADAR_ENABLED=false — 서비스 대기")
        while True:
            time.sleep(60)

    if RADAR_MODE == "presence_led":
        run_presence_led_mode()
    else:
        run_post_mode()


if __name__ == "__main__":
    main()
