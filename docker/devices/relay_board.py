"""
Waveshare RPi Relay Board control
https://www.waveshare.com/wiki/RPi_Relay_Board

3채널 릴레이 보드 — Active LOW 방식:
  GPIO LOW  (0) → 릴레이 활성 (장치 ON)
  GPIO HIGH (1) → 릴레이 비활성 (장치 OFF)

기본 GPIO 핀 (BCM):
  CH1: 26  ← LED 전등
  CH2: 20  ← 환풍기(Fan)
  CH3: 21  ← 예비

사용 전 GPIO.setmode(GPIO.BCM) 이 이미 호출되어 있어야 합니다.
(main_ctl.py 에서 초기화)
"""
import logging
import RPi.GPIO as GPIO

_initialized_pins: set = set()


def _ensure_output(pin: int) -> None:
    """핀이 OUTPUT 모드로 초기화되지 않았으면 초기화 (HIGH = OFF)."""
    if pin not in _initialized_pins:
        GPIO.setup(pin, GPIO.OUT)
        GPIO.output(pin, GPIO.HIGH)
        _initialized_pins.add(pin)
        logging.debug(f"relay_board: pin {pin} initialized (HIGH/OFF)")


def relay_on(pin: int) -> None:
    """릴레이 ON — GPIO LOW."""
    _ensure_output(pin)
    GPIO.output(pin, GPIO.LOW)
    logging.info(f"relay_board: pin {pin} → ON (LOW)")


def relay_off(pin: int) -> None:
    """릴레이 OFF — GPIO HIGH."""
    _ensure_output(pin)
    GPIO.output(pin, GPIO.HIGH)
    logging.info(f"relay_board: pin {pin} → OFF (HIGH)")


def relay_is_on(pin: int) -> bool:
    """현재 릴레이 상태 반환 (True = ON)."""
    _ensure_output(pin)
    return GPIO.input(pin) == GPIO.LOW


def relay_toggle(pin: int) -> bool:
    """릴레이 토글. 변경 후 상태 반환 (True = ON)."""
    if relay_is_on(pin):
        relay_off(pin)
        return False
    else:
        relay_on(pin)
        return True


def relay_all_off(pins: list) -> None:
    """전체 릴레이 OFF (비상 종료용)."""
    for pin in pins:
        relay_off(pin)
    logging.info(f"relay_board: all OFF → pins {pins}")
