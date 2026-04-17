#!/usr/bin/env python3
"""RCWL-0516 레이더 단독 감지 → API POST"""
import lgpio, time, os, logging, requests, threading
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("RadarCtl")

RADAR_PIN      = int(os.getenv("RADAR_GPIO_PIN", "4"))
RADAR_HOLDTIME = float(os.getenv("RADAR_HOLDTIME", "3.0"))
API_URL        = os.getenv("API_URL", "http://localhost:5000")
TERMINAL_ID    = os.getenv("TERMINAL_ID", "")
RADAR_ENABLED  = os.getenv("RADAR_ENABLED", "true").lower() == "true"
SKIP_SENDS     = os.getenv("SKIP_SENDS", "false").lower() == "true"


def post_radar(active: bool):
    if SKIP_SENDS or not RADAR_ENABLED:
        logger.info(f"[SKIP] radar active={active}")
        return
    def _send():
        try:
            count = 1 if active else 0
            requests.post(f"{API_URL}/update_count",
                          json={"count": count, "source": "radar"},
                          timeout=10)
            logger.info(f"[POST] update_count count={count} (radar active={active})")
        except Exception as e:
            logger.warning(f"POST 실패: {e}")
    threading.Thread(target=_send, daemon=True).start()


def main():
    if not RADAR_ENABLED:
        logger.info("RADAR_ENABLED=false — 서비스 대기")
        while True:
            time.sleep(60)

    h = lgpio.gpiochip_open(0)
    lgpio.gpio_claim_input(h, RADAR_PIN, lgpio.SET_PULL_UP)
    logger.info(f"레이더 감지 시작 (GPIO{RADAR_PIN})")

    prev = lgpio.gpio_read(h, RADAR_PIN)
    last_active_ts = 0.0

    try:
        while True:
            v = lgpio.gpio_read(h, RADAR_PIN)
            now = time.time()

            if v == 1 and prev == 0:
                last_active_ts = now
                logger.info(f"감지! GPIO{RADAR_PIN}")
                post_radar(True)

            elif v == 0 and last_active_ts > 0 and (now - last_active_ts) > RADAR_HOLDTIME:
                last_active_ts = 0.0
                logger.info("감지 종료")
                post_radar(False)

            prev = v
            time.sleep(0.05)

    except KeyboardInterrupt:
        logger.info("종료")
    finally:
        lgpio.gpiochip_close(h)


if __name__ == "__main__":
    main()
