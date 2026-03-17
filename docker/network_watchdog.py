import logging
import os
import time
from dotenv import load_dotenv

from logging_handler import setup_logging
from network_resilience import load_state, request_reboot, should_request_reboot

load_dotenv()

CHECK_INTERVAL_SEC = int(os.getenv("WATCHDOG_CHECK_INTERVAL_SEC", "30"))

def run_watchdog() -> None:
    last_seen_failure_count = None

    while True:
        state = load_state()
        failure_count = int(state.get("consecutive_failures", 0))
        failure_reason = state.get("last_failure_reason") or ""

        if failure_count != last_seen_failure_count:
            if failure_count > 0:
                logging.error(
                    "network_watchdog: 운영프로그램 장애 상태 감지 (%s회) reason=%s started_at=%s",
                    failure_count,
                    failure_reason,
                    state.get("failure_started_at", 0),
                )
            elif last_seen_failure_count not in (None, 0):
                logging.info("network_watchdog: 운영프로그램 장애 상태 해제 확인")
            last_seen_failure_count = failure_count

        if failure_count > 0 and should_request_reboot(state):
            request_reboot(failure_reason or "network_unhealthy", "network_watchdog")

        time.sleep(CHECK_INTERVAL_SEC)


if __name__ == "__main__":
    setup_logging("network_watchdog")
    logging.info(
        "network_watchdog: 시작 interval=%s state_file_monitoring=enabled",
        CHECK_INTERVAL_SEC,
    )
    run_watchdog()
