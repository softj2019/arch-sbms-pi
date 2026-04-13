import logging
import os
from contextlib import asynccontextmanager

import websockets


DEFAULT_DEV_WEBSOCKET_FALLBACK_URL = "ws://192.168.10.108:8080/websocket"
DEFAULT_WS_OPEN_TIMEOUT = float(os.getenv("WEBSOCKET_OPEN_TIMEOUT_SEC", "10"))
DEFAULT_WS_CLOSE_TIMEOUT = float(os.getenv("WEBSOCKET_CLOSE_TIMEOUT_SEC", "10"))
DEFAULT_WS_PING_INTERVAL = os.getenv("WEBSOCKET_PING_INTERVAL_SEC", "20")
DEFAULT_WS_PING_TIMEOUT = os.getenv("WEBSOCKET_PING_TIMEOUT_SEC", "20")


def _coerce_optional_float(value, default=None):
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    value = str(value).strip()
    if value == "":
        return default
    if value.lower() in {"none", "off", "false"}:
        return None
    return float(value)


def _build_connect_kwargs(connect_kwargs):
    merged = dict(connect_kwargs)
    merged.setdefault("open_timeout", DEFAULT_WS_OPEN_TIMEOUT)
    merged.setdefault("close_timeout", DEFAULT_WS_CLOSE_TIMEOUT)
    merged.setdefault("ping_interval", _coerce_optional_float(DEFAULT_WS_PING_INTERVAL, None))
    merged.setdefault("ping_timeout", _coerce_optional_float(DEFAULT_WS_PING_TIMEOUT, None))
    return merged


def _clean_url(url):
    if not url:
        return None
    return url.strip()


def is_dev_terminal(extracted_number):
    return str(extracted_number) == str(os.getenv("OFFICE_HOSTNAME"))


def select_primary_websocket_url(extracted_number):
    if is_dev_terminal(extracted_number):
        return _clean_url(os.getenv("DEV_WEBSOCKET_URL"))
    return _clean_url(os.getenv("PROD_WEBSOCKET_URL"))


def get_websocket_candidates(primary_url=None, extracted_number=None):
    candidates = []
    dev_url = _clean_url(os.getenv("DEV_WEBSOCKET_URL"))
    fallback_url = _clean_url(os.getenv("DEV_WEBSOCKET_FALLBACK_URL")) or DEFAULT_DEV_WEBSOCKET_FALLBACK_URL

    if primary_url:
        candidates.append(_clean_url(primary_url))
    elif extracted_number is not None:
        candidates.append(select_primary_websocket_url(extracted_number))

    if candidates and candidates[0] == dev_url and fallback_url:
        candidates.append(fallback_url)

    unique_candidates = []
    for candidate in candidates:
        if candidate and candidate not in unique_candidates:
            unique_candidates.append(candidate)
    return unique_candidates


@asynccontextmanager
async def websocket_connection(primary_url=None, extracted_number=None, log_context=None, **connect_kwargs):
    candidates = get_websocket_candidates(primary_url=primary_url, extracted_number=extracted_number)
    if not candidates:
        raise ValueError("WebSocket URL is not configured")

    resolved_connect_kwargs = _build_connect_kwargs(connect_kwargs)
    last_error = None
    for candidate in candidates:
        try:
            websocket = await websockets.connect(candidate, **resolved_connect_kwargs)
            if log_context and candidate != candidates[0]:
                logging.warning(f"{log_context}: fallback WebSocket 연결 성공 ({candidate})")
            try:
                yield websocket
            finally:
                await websocket.close()
            return
        except Exception as exc:
            last_error = exc
            if log_context:
                logging.warning(f"{log_context}: WebSocket 연결 실패 ({candidate}): {exc}")

    raise last_error
