#!/usr/bin/env python3
"""Trigger the waiting-count API when a GPIO input is shorted by a button.

Default wiring matches the current board discussion:
- physical pin 25: GND
- physical pin 26: BCM GPIO7

When GPIO7 is pulled LOW by the button, this script POSTs {"count": 1} to
/update_count exactly once per press event, then waits for the line to return
to HIGH before arming again.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import time

import requests
import RPi.GPIO as GPIO


DEFAULT_API_URL = "http://localhost:5000/update_count"
DEFAULT_BCM_PIN = 7  # physical pin 26
DEFAULT_MESSAGE = "교통약자"
DEFAULT_SOURCE = "button"
DEFAULT_COLOR = "01"

running = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Watch a GPIO input and trigger count=1 on a button short."
    )
    parser.add_argument(
        "--bcm-pin",
        type=int,
        default=DEFAULT_BCM_PIN,
        help="BCM GPIO input pin to monitor. Default: 7 (physical pin 26).",
    )
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help=f"POST target. Default: {DEFAULT_API_URL}",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Count value to send in the JSON payload. Default: 1.",
    )
    parser.add_argument(
        "--message",
        default=DEFAULT_MESSAGE,
        help=f"Message override sent to update_count. Default: {DEFAULT_MESSAGE}",
    )
    parser.add_argument(
        "--source",
        default=DEFAULT_SOURCE,
        help=f"Source tag sent to update_count. Default: {DEFAULT_SOURCE}",
    )
    parser.add_argument(
        "--color",
        default=DEFAULT_COLOR,
        help=f"Color code sent to update_count. Default: {DEFAULT_COLOR}",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="HTTP request timeout in seconds. Default: 5.",
    )
    parser.add_argument(
        "--debounce-ms",
        type=int,
        default=300,
        help="Edge debounce in milliseconds. Default: 300.",
    )
    parser.add_argument(
        "--settle-ms",
        type=int,
        default=50,
        help="Delay after edge detection before confirming HIGH. Default: 50.",
    )
    parser.add_argument(
        "--poll-ms",
        type=int,
        default=100,
        help="Idle poll interval for edge wait timeout. Default: 100.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Log the trigger instead of sending the HTTP request.",
    )
    return parser.parse_args()


def handle_signal(signum, _frame) -> None:
    global running
    logging.info("signal received: %s, shutting down", signum)
    running = False


def trigger(api_url: str, count: int, message: str, source: str, color: str, timeout: float, dry_run: bool) -> None:
    payload = {"count": count, "message": message, "source": source, "color": color}

    if dry_run:
        logging.info("dry-run trigger: POST %s payload=%s", api_url, payload)
        return

    response = requests.post(api_url, json=payload, timeout=timeout)
    response.raise_for_status()
    logging.info(
        "trigger sent: status=%s body=%s",
        response.status_code,
        response.text.strip(),
    )


def process_trigger_cycle(args: argparse.Namespace, use_edge_wait: bool) -> None:
    time.sleep(args.settle_ms / 1000.0)
    if GPIO.input(args.bcm_pin) != GPIO.LOW:
        logging.info("edge ignored: pin returned HIGH during settle window")
        return

    try:
        trigger(args.api_url, args.count, args.message, args.source, args.color, args.timeout, args.dry_run)
    except Exception as exc:
        logging.error("trigger failed: %s", exc)

    while running and GPIO.input(args.bcm_pin) == GPIO.LOW:
        time.sleep(0.05)

    logging.info("input released, re-armed")


def main() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(args.bcm_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    logging.info(
        "watching BCM GPIO%s for short-to-GND button events, target=%s",
        args.bcm_pin,
        args.api_url,
    )

    was_low = GPIO.input(args.bcm_pin) == GPIO.LOW
    use_edge_wait = not was_low

    if was_low:
        logging.info("input is already LOW at startup, treating it as an active press")
        process_trigger_cycle(args, use_edge_wait=False)
        was_low = False

    try:
        while running:
            if use_edge_wait:
                try:
                    channel = GPIO.wait_for_edge(
                        args.bcm_pin,
                        GPIO.FALLING,
                        timeout=args.poll_ms,
                        bouncetime=args.debounce_ms,
                    )
                except RuntimeError as exc:
                    use_edge_wait = False
                    logging.warning("edge wait unavailable, falling back to polling: %s", exc)
                    time.sleep(args.poll_ms / 1000.0)
                    continue

                if channel is None:
                    continue
            else:
                is_low = GPIO.input(args.bcm_pin) == GPIO.LOW
                if not is_low or was_low:
                    was_low = is_low
                    time.sleep(args.poll_ms / 1000.0)
                    continue
                was_low = True

            process_trigger_cycle(args, use_edge_wait)
            if not use_edge_wait:
                was_low = False
    finally:
        GPIO.cleanup(args.bcm_pin)
        logging.info("GPIO cleanup complete")

    return 0


if __name__ == "__main__":
    sys.exit(main())
