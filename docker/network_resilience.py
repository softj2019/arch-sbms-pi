import json
import logging
import os
import shlex
import subprocess
import threading
import time
from datetime import datetime
from pathlib import Path

import psutil
from dotenv import load_dotenv

load_dotenv()

STATE_FILE = Path(os.getenv("WATCHDOG_STATE_FILE", "/home/admin/gunpo/docker/run/network_watchdog_state.json"))
NETWORK_RETRY_INTERVAL_SEC = int(os.getenv("NETWORK_RETRY_INTERVAL_SEC", "10"))
NETWORK_OVERVIEW_INTERVAL_SEC = int(os.getenv("NETWORK_OVERVIEW_INTERVAL_SEC", str(NETWORK_RETRY_INTERVAL_SEC)))
NETWORK_FAILURE_REBOOT_THRESHOLD = int(os.getenv("NETWORK_FAILURE_REBOOT_THRESHOLD", "10"))
BOOT_GRACE_SEC = int(os.getenv("WATCHDOG_BOOT_GRACE_SEC", "180"))
REBOOT_COOLDOWN_SEC = int(os.getenv("WATCHDOG_REBOOT_COOLDOWN_SEC", "300"))
REBOOT_COMMAND = os.getenv("WATCHDOG_REBOOT_COMMAND", "sudo reboot")
MAX_PENDING_EVENTS = int(os.getenv("NETWORK_EVENT_MAX_QUEUE", "50"))
MAX_PENDING_OUTAGE_LOGS = int(os.getenv("NETWORK_OUTAGE_LOG_MAX_QUEUE", "200"))
MAX_PROBE_HISTORY = int(os.getenv("NETWORK_PROBE_HISTORY_LIMIT", "120"))
_OUTAGE_LOG_CAPTURE = threading.local()


def _initial_state() -> dict:
    return {
        "consecutive_failures": 0,
        "last_failure_reason": None,
        "last_reboot_request_at": 0,
        "last_healthy_at": 0,
        "last_checked_at": 0,
        "failure_started_at": 0,
        "last_recovered_at": 0,
        "pending_events": [],
        "pending_outage_logs": [],
        "recent_probes": [],
        "last_probe_snapshot": {},
    }


def now_epoch() -> int:
    return int(time.time())


def isoformat_epoch(epoch_seconds: int | float | None) -> str:
    if not epoch_seconds:
        return ""
    return datetime.fromtimestamp(epoch_seconds).isoformat(timespec="seconds")


def load_state() -> dict:
    if not STATE_FILE.exists():
        return _initial_state()

    try:
        with STATE_FILE.open("r", encoding="utf-8") as fp:
            state = json.load(fp)
    except (json.JSONDecodeError, OSError) as exc:
        logging.error("network_resilience: 상태 파일 로드 실패: %s", exc)
        state = _initial_state()
        state["last_failure_reason"] = "state_load_failed"

    merged = _initial_state()
    merged.update(state)
    if not isinstance(merged.get("pending_events"), list):
        merged["pending_events"] = []
    if not isinstance(merged.get("pending_outage_logs"), list):
        merged["pending_outage_logs"] = []
    if not isinstance(merged.get("recent_probes"), list):
        merged["recent_probes"] = []
    if not isinstance(merged.get("last_probe_snapshot"), dict):
        merged["last_probe_snapshot"] = {}
    return merged


def save_state(state: dict) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        temp_path = STATE_FILE.with_suffix(".tmp")
        with temp_path.open("w", encoding="utf-8") as fp:
            json.dump(state, fp, ensure_ascii=True, indent=2)
        temp_path.replace(STATE_FILE)
    except OSError as exc:
        logging.error("network_resilience: 상태 파일 저장 실패: %s", exc)


def seconds_since_boot() -> int:
    return int(time.time() - psutil.boot_time())


def _append_event(state: dict, event: dict) -> None:
    pending_events = list(state.get("pending_events", []))
    pending_events.append(event)
    if len(pending_events) > MAX_PENDING_EVENTS:
        pending_events = pending_events[-MAX_PENDING_EVENTS:]
    state["pending_events"] = pending_events


def _append_probe_snapshot(state: dict, snapshot: dict) -> None:
    recent_probes = list(state.get("recent_probes", []))
    recent_probes.append(snapshot)
    if len(recent_probes) > MAX_PROBE_HISTORY:
        recent_probes = recent_probes[-MAX_PROBE_HISTORY:]
    state["recent_probes"] = recent_probes
    state["last_probe_snapshot"] = snapshot


def _append_outage_log(state: dict, log_entry: dict) -> None:
    pending_outage_logs = list(state.get("pending_outage_logs", []))
    pending_outage_logs.append(log_entry)
    if len(pending_outage_logs) > MAX_PENDING_OUTAGE_LOGS:
        pending_outage_logs = pending_outage_logs[-MAX_PENDING_OUTAGE_LOGS:]
    state["pending_outage_logs"] = pending_outage_logs


def _build_probe_snapshot(network_status, source: str, current_time: int, retry_count: int) -> dict:
    return {
        "source": source,
        "checked_at": current_time,
        "checked_at_iso": isoformat_epoch(current_time),
        "healthy": bool(network_status.healthy),
        "failure_reason": network_status.failure_reason or "",
        "retry_count": retry_count,
        "router_gateway": network_status.router_gateway or "",
        "router_gateway_ok": bool(network_status.router_gateway_ok),
        "router_wan_ip": network_status.router_wan_ip or "",
        "public_ip": network_status.public_ip or "",
        "lte_router_connected": bool(network_status.lte_router_connected),
        "outbound_ok": bool(network_status.outbound_ok),
    }


def update_network_state(network_status, source: str) -> dict:
    state = load_state()
    current_time = now_epoch()
    state["last_checked_at"] = current_time
    next_retry_count = 0 if network_status.healthy else int(state.get("consecutive_failures", 0)) + 1
    probe_snapshot = _build_probe_snapshot(network_status, source, current_time, next_retry_count)
    _append_probe_snapshot(state, probe_snapshot)

    logging.info(
        "network_resilience: diagnostic source=%s healthy=%s retry=%s gateway_ok=%s lte_link=%s outbound_ok=%s wan_ip=%s public_ip=%s reason=%s",
        source,
        "Y" if network_status.healthy else "N",
        next_retry_count,
        "Y" if network_status.router_gateway_ok else "N",
        "Y" if network_status.lte_router_connected else "N",
        "Y" if network_status.outbound_ok else "N",
        network_status.router_wan_ip or "",
        network_status.public_ip or "",
        network_status.failure_reason or "",
    )

    if network_status.healthy:
        if state.get("consecutive_failures", 0) > 0:
            recovered_event = {
                "event_type": "network_restored",
                "source": source,
                "occurred_at": current_time,
                "occurred_at_iso": isoformat_epoch(current_time),
                "failure_started_at": int(state.get("failure_started_at", 0) or 0),
                "failure_started_at_iso": isoformat_epoch(state.get("failure_started_at", 0)),
                "recovered_at": current_time,
                "recovered_at_iso": isoformat_epoch(current_time),
                "failure_reason": state.get("last_failure_reason") or "",
                "retry_count": int(state.get("consecutive_failures", 0)),
                "duration_sec": max(0, current_time - int(state.get("failure_started_at", 0) or current_time)),
            }
            _append_event(state, recovered_event)

        state["consecutive_failures"] = 0
        state["last_failure_reason"] = None
        state["last_healthy_at"] = current_time
        state["last_recovered_at"] = current_time
        state["failure_started_at"] = 0
        save_state(state)
        return state

    if int(state.get("consecutive_failures", 0)) == 0:
        state["failure_started_at"] = current_time
        down_event = {
            "event_type": "network_down",
            "source": source,
            "occurred_at": current_time,
            "occurred_at_iso": isoformat_epoch(current_time),
            "failure_reason": network_status.failure_reason or "",
            "router_wan_ip": network_status.router_wan_ip or "",
            "public_ip": network_status.public_ip or "",
            "outbound_ok": bool(network_status.outbound_ok),
        }
        _append_event(state, down_event)

    state["consecutive_failures"] = int(state.get("consecutive_failures", 0)) + 1
    state["last_failure_reason"] = network_status.failure_reason
    save_state(state)
    return state


def should_request_reboot(state: dict) -> bool:
    if int(state.get("consecutive_failures", 0)) < NETWORK_FAILURE_REBOOT_THRESHOLD:
        return False
    if seconds_since_boot() < BOOT_GRACE_SEC:
        logging.warning(
            "network_resilience: 부팅 유예 시간 내 장애 감지. 재부팅 연기 (%ss/%ss)",
            seconds_since_boot(),
            BOOT_GRACE_SEC,
        )
        return False

    last_reboot_request_at = int(state.get("last_reboot_request_at", 0) or 0)
    elapsed = now_epoch() - last_reboot_request_at
    if elapsed < REBOOT_COOLDOWN_SEC:
        logging.warning(
            "network_resilience: 재부팅 쿨다운 중. 다음 재시도까지 %ss 남음",
            REBOOT_COOLDOWN_SEC - elapsed,
        )
        return False
    return True


def request_reboot(reason: str, source: str) -> dict:
    state = load_state()
    current_time = now_epoch()
    state["last_reboot_request_at"] = current_time
    reboot_event = {
        "event_type": "reboot_requested",
        "source": source,
        "occurred_at": current_time,
        "occurred_at_iso": isoformat_epoch(current_time),
        "failure_reason": reason or "",
        "retry_count": int(state.get("consecutive_failures", 0)),
    }
    _append_event(state, reboot_event)
    save_state(state)
    logging.critical("network_resilience: 네트워크 장애 지속으로 시스템 재부팅 요청: %s", reason)
    os.sync()

    try:
        subprocess.run(shlex.split(REBOOT_COMMAND), check=False)
    except Exception as exc:
        logging.error("network_resilience: 재부팅 명령 실행 실패: %s", exc)
    return state


def record_outage_log(level: str, logger_name: str, message: str, created_at: float | None = None) -> None:
    if getattr(_OUTAGE_LOG_CAPTURE, "active", False):
        return

    _OUTAGE_LOG_CAPTURE.active = True
    state = load_state()
    try:
        if int(state.get("consecutive_failures", 0)) <= 0 and not int(state.get("failure_started_at", 0) or 0):
            return

        occurred_at = int(created_at or time.time())
        _append_outage_log(
            state,
            {
                "occurred_at": occurred_at,
                "occurred_at_iso": isoformat_epoch(occurred_at),
                "level": level,
                "logger": logger_name,
                "message": message,
            },
        )
        save_state(state)
    finally:
        _OUTAGE_LOG_CAPTURE.active = False


def mark_events_delivered() -> None:
    state = load_state()
    if not state.get("pending_events") and not state.get("pending_outage_logs"):
        return
    state["pending_events"] = []
    state["pending_outage_logs"] = []
    save_state(state)


def build_runtime_fields(network_status, include_pending_events: bool = False) -> dict:
    state = load_state()
    pending_events = state.get("pending_events", [])
    pending_outage_logs = state.get("pending_outage_logs", [])
    recent_probes = state.get("recent_probes", [])
    fields = {
        "network_retry_count": str(int(state.get("consecutive_failures", 0))),
        "network_outage_started_at": isoformat_epoch(state.get("failure_started_at", 0)),
        "network_last_recovered_at": isoformat_epoch(state.get("last_recovered_at", 0)),
        "network_last_reboot_requested_at": isoformat_epoch(state.get("last_reboot_request_at", 0)),
        "network_pending_event_count": str(len(pending_events)),
        "network_outage_log_count": str(len(pending_outage_logs)),
        "network_recent_diagnostic_count": str(len(recent_probes)),
        "network_retry_interval_sec": str(NETWORK_RETRY_INTERVAL_SEC),
        "network_overview_interval_sec": str(NETWORK_OVERVIEW_INTERVAL_SEC),
        "network_reboot_threshold": str(NETWORK_FAILURE_REBOOT_THRESHOLD),
        "network_failure_reason": network_status.failure_reason or state.get("last_failure_reason") or "",
        "network_last_checked_at": isoformat_epoch(state.get("last_checked_at", 0)),
    }
    if include_pending_events:
        fields["network_event_logs"] = json.dumps(pending_events, ensure_ascii=True, separators=(",", ":"))
        fields["network_outage_logs"] = pending_outage_logs
        fields["network_recent_diagnostics"] = json.dumps(
            recent_probes[-20:],
            ensure_ascii=True,
            separators=(",", ":"),
        )
    return fields
