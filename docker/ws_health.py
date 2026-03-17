"""WebSocket health heartbeat tracker (in-memory, thread-safe).

STOMP client threads call ``report_ws_alive`` on every successful
WebSocket operation.  The watchdog thread in *main_ctl* polls
``is_ws_healthy`` to decide whether the process should be recycled.
"""

import logging
import time
import threading

_lock = threading.Lock()
_heartbeats: dict[str, float] = {}

logger = logging.getLogger("ws_health")


def report_ws_alive(source: str) -> None:
    with _lock:
        _heartbeats[source] = time.monotonic()


def is_ws_healthy(timeout_sec: int = 60) -> bool:
    now = time.monotonic()
    with _lock:
        if not _heartbeats:
            return True  # no source reported yet -> startup grace
        return any(now - ts < timeout_sec for ts in _heartbeats.values())


def get_ws_health() -> dict:
    now = time.monotonic()
    with _lock:
        return {src: round(now - ts, 1) for src, ts in _heartbeats.items()}
