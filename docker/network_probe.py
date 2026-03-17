import base64
import logging
import os
import re
import socket
import urllib.parse
from dataclasses import asdict, dataclass

import requests
from dotenv import load_dotenv

load_dotenv()

DEFAULT_ROUTER_STATUS_URL = os.getenv("LTE_ROUTER_STATUS_URL", "http://192.168.10.254/status_wanlink.asp")
DEFAULT_PUBLIC_IP_SERVICES = (
    "https://api64.ipify.org?format=json",
    "https://ifconfig.me/ip",
    "https://checkip.amazonaws.com",
)
DEFAULT_EGRESS_TARGETS = (
    ("1.1.1.1", 53),
    ("8.8.8.8", 53),
)


@dataclass
class NetworkStatus:
    router_gateway: str | None
    router_gateway_ok: bool
    router_wan_ip: str | None
    public_ip: str | None
    lte_router_connected: bool
    outbound_ok: bool
    healthy: bool
    failure_reason: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def _parse_csv_env(value: str | None, default: tuple[str, ...]) -> tuple[str, ...]:
    if not value:
        return default
    items = tuple(item.strip() for item in value.split(",") if item.strip())
    return items or default


def _parse_egress_targets(value: str | None) -> tuple[tuple[str, int], ...]:
    if not value:
        return DEFAULT_EGRESS_TARGETS

    targets: list[tuple[str, int]] = []
    for item in value.split(","):
        item = item.strip()
        if not item or ":" not in item:
            continue
        host, port = item.rsplit(":", 1)
        try:
            targets.append((host.strip(), int(port)))
        except ValueError:
            logging.warning("network_probe: 잘못된 WATCHDOG_EGRESS_TARGETS 항목 무시: %s", item)
    return tuple(targets) or DEFAULT_EGRESS_TARGETS


def get_public_ip_services() -> tuple[str, ...]:
    return _parse_csv_env(os.getenv("PUBLIC_IP_SERVICES"), DEFAULT_PUBLIC_IP_SERVICES)


def get_egress_targets() -> tuple[tuple[str, int], ...]:
    return _parse_egress_targets(os.getenv("WATCHDOG_EGRESS_TARGETS"))


def _build_basic_auth_header(raw_credential: str | None) -> dict[str, str]:
    if not raw_credential:
        return {}
    encoded = base64.b64encode(raw_credential.encode("utf-8")).decode("utf-8")
    return {"Authorization": f"Basic {encoded}"}


def _split_basic_credential(raw_credential: str | None) -> tuple[str, str] | None:
    if not raw_credential or ':' not in raw_credential:
        return None
    username, password = raw_credential.split(':', 1)
    return username, password


def _request_router_status(router_status_url: str, credential: str | None, timeout: int | float):
    headers = _build_basic_auth_header(credential)
    try:
        response = requests.get(router_status_url, headers=headers, timeout=timeout)
        if response.status_code != 401:
            return response

        split_credential = _split_basic_credential(credential)
        if not split_credential:
            return response

        logging.warning('network_probe: 기본 Authorization 헤더 인증 실패(401). requests auth 방식으로 재시도합니다.')
        return requests.get(router_status_url, auth=split_credential, timeout=timeout)
    except requests.RequestException:
        raise


def get_router_gateway(router_status_url: str | None = None) -> str | None:
    router_status_url = router_status_url or DEFAULT_ROUTER_STATUS_URL
    parsed = urllib.parse.urlparse(router_status_url)
    return parsed.hostname


def fetch_router_wan_ip(
    credential: str | None = None,
    router_status_url: str | None = None,
    timeout: int | float = 5,
) -> str | None:
    credential = credential or os.getenv("ORIGINAL_STR")
    router_status_url = router_status_url or DEFAULT_ROUTER_STATUS_URL
    if not credential:
        logging.error("network_probe: ORIGINAL_STR 미설정으로 LTE 라우터 인증 헤더를 만들 수 없습니다.")
        return None

    try:
        response = _request_router_status(router_status_url, credential, timeout)
        response.raise_for_status()
        match = re.search(r"function\s+wanlink_ip4_wan\(\)\s*{\s*return\s+'([\d\.]+)';\s*}", response.text)
        if match:
            return match.group(1)
        logging.warning("network_probe: LTE 라우터 응답에서 WAN IP를 찾을 수 없습니다.")
        return None
    except requests.RequestException as exc:
        logging.error("network_probe: LTE 라우터 WAN IP 조회 실패: %s", exc)
        return None


def can_reach_router_gateway(
    credential: str | None = None,
    router_status_url: str | None = None,
    timeout: int | float = 5,
) -> bool:
    credential = credential or os.getenv("ORIGINAL_STR")
    router_status_url = router_status_url or DEFAULT_ROUTER_STATUS_URL
    try:
        response = _request_router_status(router_status_url, credential, timeout)
        return response.status_code < 500
    except requests.RequestException as exc:
        logging.warning("network_probe: LTE 라우터 게이트웨이 통신 실패: %s", exc)
        return False


def fetch_public_ip(timeout: int | float = 5, services: tuple[str, ...] | None = None) -> str | None:
    services = services or get_public_ip_services()
    for service in services:
        try:
            response = requests.get(service, timeout=timeout)
            response.raise_for_status()
            text = response.text.strip()
            if service.endswith("format=json"):
                data = response.json()
                text = data.get("ip", "").strip()
            if text:
                return text
        except requests.RequestException as exc:
            logging.warning("network_probe: 공인 IP 조회 실패(%s): %s", service, exc)
    return None


def can_send_outbound_packet(
    targets: tuple[tuple[str, int], ...] | None = None,
    timeout: int | float = 3,
) -> bool:
    targets = targets or get_egress_targets()
    for host, port in targets:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True
        except OSError as exc:
            logging.warning("network_probe: 외부 송신 실패(%s:%s): %s", host, port, exc)
    return False


def collect_network_status() -> NetworkStatus:
    router_gateway = get_router_gateway()
    router_gateway_ok = can_reach_router_gateway()
    router_wan_ip = fetch_router_wan_ip()
    lte_router_connected = bool(router_wan_ip)
    outbound_ok = can_send_outbound_packet()
    public_ip = fetch_public_ip() if outbound_ok else None

    failure_reasons: list[str] = []
    if not router_gateway_ok:
        failure_reasons.append("router_gateway_unreachable")
    if not lte_router_connected:
        failure_reasons.append("wan_ip_unavailable")
    if not outbound_ok:
        failure_reasons.append("outbound_unreachable")

    healthy = not failure_reasons
    return NetworkStatus(
        router_gateway=router_gateway,
        router_gateway_ok=router_gateway_ok,
        router_wan_ip=router_wan_ip,
        public_ip=public_ip,
        lte_router_connected=lte_router_connected,
        outbound_ok=outbound_ok,
        healthy=healthy,
        failure_reason=",".join(failure_reasons) if failure_reasons else None,
    )
