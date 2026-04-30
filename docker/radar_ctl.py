#!/usr/bin/env python3
"""RCWL-0516 레이더 단독 감지 → API POST / LED 릴레이 재실 제어"""
import os, sys, time, logging, requests, threading
from datetime import datetime
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
LED_SCHEDULE_ON   = os.getenv("LED_SCHEDULE_ON",  "17:30")
LED_SCHEDULE_OFF  = os.getenv("LED_SCHEDULE_OFF", "05:30")

import RPi.GPIO as GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)
GPIO.setup(RADAR_PIN, GPIO.IN)

sys.path.insert(0, os.path.dirname(__file__))
from devices.relay_board import relay_on, relay_off

# ── 스케줄 오버라이드 (운영 프로그램 구독으로 런타임 변경 가능) ──
# None이면 .env 값 사용. 외부에서 update_schedule_override() 호출로 덮어씀.
_schedule_override: dict = {"on": None, "off": None}

def update_schedule_override(on_time: str | None, off_time: str | None):
    """STOMP/구독으로 받은 설정값으로 스케줄 오버라이드. None 전달 시 .env 값으로 복구."""
    _schedule_override["on"]  = on_time
    _schedule_override["off"] = off_time
    logger.info(f"[스케줄 오버라이드] ON={on_time or LED_SCHEDULE_ON}, OFF={off_time or LED_SCHEDULE_OFF}")


def _parse_hm(t_str: str) -> int:
    h, m = map(int, t_str.strip().split(":"))
    return h * 60 + m

def _in_window(now_min: int, on_min: int, off_min: int) -> bool:
    if on_min <= off_min:
        return on_min <= now_min < off_min
    # 자정 넘는 구간 (예: 17:30 ~ 05:30)
    return now_min >= on_min or now_min < off_min


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
                if v == 1 and prev_v == 0:
                    led_off_time = now + PRESENCE_DURATION
                    detect_logger.info(f"[DETECT] ON  GPIO{RADAR_PIN} → 타이머 연장 ({PRESENCE_DURATION}s)")
                elif v == 1:
                    led_off_time = now + PRESENCE_DURATION
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


def run_schedule_led_mode():
    logger.info(f"[시간 스케줄 LED 모드] 기본 ON={LED_SCHEDULE_ON}, OFF={LED_SCHEDULE_OFF}, 릴레이 핀=GPIO{PRESENCE_LED_PIN}")
    relay_off(PRESENCE_LED_PIN)
    led_state = False

    try:
        while True:
            on_str  = _schedule_override["on"]  or LED_SCHEDULE_ON
            off_str = _schedule_override["off"] or LED_SCHEDULE_OFF
            on_min  = _parse_hm(on_str)
            off_min = _parse_hm(off_str)

            now = datetime.now()
            now_min = now.hour * 60 + now.minute
            should_on = _in_window(now_min, on_min, off_min)

            if should_on and not led_state:
                relay_on(PRESENCE_LED_PIN)
                led_state = True
                led_logger.info(f"[LED] ON  GPIO{PRESENCE_LED_PIN} (스케줄 {on_str}~{off_str})")
            elif not should_on and led_state:
                relay_off(PRESENCE_LED_PIN)
                led_state = False
                led_logger.info(f"[LED] OFF GPIO{PRESENCE_LED_PIN} (스케줄 종료 {on_str}~{off_str})")

            time.sleep(30)

    except KeyboardInterrupt:
        relay_off(PRESENCE_LED_PIN)
        logger.info("종료")
    finally:
        GPIO.cleanup()


def main():
    # time_led 모드는 RADAR_ENABLED 무관하게 실행 (레이더 불필요)
    if RADAR_MODE == "time_led":
        run_schedule_led_mode()
        return

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
