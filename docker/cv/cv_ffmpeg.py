import os
import time
import sys
import cv2
import torch
import threading
import subprocess
import socket
import urllib.request
import urllib.parse
import requests
import json
import re
import logging
import atexit
import signal
import asyncio
import websockets
from datetime import datetime
from dotenv import load_dotenv, dotenv_values
from ultralytics import YOLO
from dataclasses import dataclass, field
from collections import deque
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
import json as _json

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.append(PROJECT_ROOT)

from websocket_endpoint import select_primary_websocket_url, websocket_connection

# ── 기본 설정 로딩 ────────────────────────────────────────────
load_dotenv()

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
custom_env_path = os.path.join(project_root, ".env_custom")
custom_env = dotenv_values(custom_env_path)
for key, value in custom_env.items():
    os.environ[key] = value

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("PeopleDetector")

# ── Phase 1: ENV 설정 ─────────────────────────────────────────
ENV_TYPE          = os.getenv("ENV_TYPE", "prod").lower()        # dev|prod  (디버그 스트림 ON/OFF)
SKIP_SENDS        = os.getenv("SKIP_SENDS", "false").lower() == "true"  # Mac 테스트용 전체 스킵
MODE              = os.getenv("MODE", "prod").lower()  # debug|prod
CAMERA_ENABLED    = os.getenv("CAMERA_ENABLED", "true").lower() == "true"   # RTSP/YOLO 사용 여부
SENSOR_MODE       = os.getenv("SENSOR_MODE", "both").lower()     # camera|radar|both
FUSION_MODE       = os.getenv("FUSION_MODE", "confirm").lower()  # gating|confirm
CV_SOURCE         = os.getenv("CV_SOURCE", "ffmpeg")             # ffmpeg|video|image
CV_SOURCE_PATH    = os.getenv("CV_SOURCE_PATH", "")
RADAR_SOURCE      = os.getenv("RADAR_SOURCE", "gpio")            # gpio|keyboard|file|disabled
RADAR_MOCK_FILE   = os.getenv("RADAR_MOCK_FILE", "/tmp/radar_tick")
DEBUG_STREAM_PORT = int(os.getenv("DEBUG_STREAM_PORT", "8089"))
CONFIRM_WINDOW    = float(os.getenv("CONFIRM_WINDOW", "5.0"))
CONFIRM_HITS      = int(os.getenv("CONFIRM_HITS", "2"))

# ── 기존 설정 ─────────────────────────────────────────────────
SERVER_API_URL = os.getenv("SERVER_API_URL")
USERNAME_OPENCV = os.getenv("USERNAME_OPENCV")
PASSWORD_OPENCV = os.getenv("PASSWORD_OPENCV")
camera_ip = os.getenv("IP_OPENCV")
hostname = socket.gethostname()
match = re.search(r"gunpo-(\d+)", hostname)
TERMINAL_ID = match.group(1) if match else os.getenv("TERMINAL_ID")
STOMP_URL = select_primary_websocket_url(TERMINAL_ID)

RADAR_PIN              = int(os.getenv("RADAR_GPIO_PIN", "3"))
RADAR_HOLDTIME         = float(os.getenv("RADAR_HOLDTIME", "3.0"))
RADAR_FALLBACK_INTERVAL = float(os.getenv("RADAR_FALLBACK_INTERVAL", "15.0"))

# ── 데이터 경로 ───────────────────────────────────────────────
if os.name == "nt":
    DATA_DIR = "D:\\download\\data"
elif sys.platform == "darwin" and CV_SOURCE != "ffmpeg":
    DATA_DIR = os.path.expanduser("~/.cache/sbms-cv")
else:
    DATA_DIR = "/home/admin/data"

os.makedirs(DATA_DIR, exist_ok=True)
if os.name != "nt":
    os.chmod(DATA_DIR, 0o755)

capture_path = os.path.join(DATA_DIR, "capture.jpg")
debug_dir    = os.path.join(DATA_DIR, "debug_images")
os.makedirs(debug_dir, exist_ok=True)

STAT_FILE_PATH = os.path.join(DATA_DIR, "stat_data.json")

# ── stat 유틸 ─────────────────────────────────────────────────
def save_stat_count(stat_people_count):
    try:
        with open(STAT_FILE_PATH, "w") as file:
            json.dump({"stat_people_count": stat_people_count}, file)
    except Exception as e:
        logger.error(f"stat_people_count 저장 오류: {e}")

def load_stat_count():
    if os.path.exists(STAT_FILE_PATH):
        try:
            with open(STAT_FILE_PATH, "r") as file:
                data = json.load(file)
                return data.get("stat_people_count", 0)
        except Exception as e:
            logger.error(f"stat_people_count 로드 오류: {e}")
    return 0

# ── YOLO 모델 로딩 ────────────────────────────────────────────
SCRIPT_DIR = "d:/download/yolo" if os.name == "nt" else DATA_DIR
MODEL_PATH = os.path.join(SCRIPT_DIR, "yolo11n.pt")
if not os.path.exists(MODEL_PATH):
    MODEL_PATH = os.path.join(SCRIPT_DIR, "yolov8n.pt")
if not os.path.exists(MODEL_PATH):
    logger.info("YOLO 모델 다운로드 시작...")
    url = "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt"
    os.makedirs(SCRIPT_DIR, exist_ok=True)
    urllib.request.urlretrieve(url, MODEL_PATH)
    logger.info("YOLO 모델 다운로드 완료")

device = "cuda" if torch.cuda.is_available() else "cpu"
logger.info(f"Using device: {device}")
model = YOLO(MODEL_PATH).to(device)

# ── 교통약자 전용 파인튜닝 모델 (듀얼 모델) ──────────────────
MOBILITY_MODEL_PATH = os.path.join(DATA_DIR, "mobility_yolo11n_best.pt")
if os.path.exists(MOBILITY_MODEL_PATH):
    mobility_model = YOLO(MOBILITY_MODEL_PATH).to(device)
    logger.info(f"교통약자 모델 로딩 완료: {MOBILITY_MODEL_PATH}")
else:
    mobility_model = None
    logger.warning(f"교통약자 모델 없음 ({MOBILITY_MODEL_PATH}) — 기본 모델로 대체")

# ── 교통약자 추론 주기 설정 (N프레임마다 1회) ─────────────────
MOBILITY_INFER_INTERVAL = int(os.getenv("MOBILITY_INFER_INTERVAL", "5"))
_mobility_frame_counter = 0
_last_mobility_found: list = []

# ── 감지 대상 클래스 필터 ──────────────────────────────────────
# .env MOBILITY_CLASSES=휠체어,목발  (쉼표 구분, 미설정 시 전체 허용)
# 가용 클래스: 휠체어 | 목발
_mobility_classes_raw = os.getenv("MOBILITY_CLASSES", "")
MOBILITY_ALLOWED_CLASSES: set[str] = (
    {c.strip() for c in _mobility_classes_raw.split(",") if c.strip()}
    if _mobility_classes_raw.strip()
    else set()   # 빈 set = 필터 없음 (전체 허용)
)
logger.info(f"교통약자 감지 클래스: {MOBILITY_ALLOWED_CLASSES or '전체'}")

API_URL = os.getenv("API_URL")
server_url = f"{API_URL}/update_count"
encoded_password = urllib.parse.quote(PASSWORD_OPENCV) if PASSWORD_OPENCV else ""
rtsp_url = os.getenv("RTSP_URL") or f"rtsp://{USERNAME_OPENCV}:{encoded_password}@{camera_ip}/stream1"
logger.info(f"RTSP URL: {rtsp_url}")

# ── Phase 1: AppState ─────────────────────────────────────────
@dataclass
class AppState:
    last_count: int = 0
    previous_count: int = 0
    stat_people_count: int = 0
    last_radar_ts: float = 0.0
    last_post_ts: float = 0.0
    last_frame_annotated: object = None   # np.ndarray with YOLO overlay
    last_frame_raw: object = None          # np.ndarray raw (no overlay, 30fps)
    fps_ewma: float = 0.0
    radar_history: deque = field(default_factory=lambda: deque(maxlen=20))
    # confirm mode state
    pending_hits: int = 0
    pending_until: float = 0.0
    committed_count: int = 0
    last_inference_ms: float = 0.0
    source: str = "camera"
    active_mode: str = "camera"
    stream_enabled: bool = True

# ── Phase 2A: RadarSource 추상화 ──────────────────────────────
class RadarSource:
    def start(self): pass
    def wait(self, timeout) -> bool: return False
    def is_active(self) -> bool:
        return False
    def cleanup(self): pass


class GpioRadarSource(RadarSource):
    """RCWL-0516 GPIO 감지 — lgpio 우선, 실패 시 RPi.GPIO 폴백."""

    def __init__(self):
        self._event = threading.Event()
        self._enabled = False
        self._last_ts = 0.0
        self._handle = None   # lgpio handle
        self._poll_thread = None

    def start(self):
        if self._try_lgpio():
            return
        if self._try_rpigpio():
            return
        logger.warning("GPIO 초기화 실패 — 레이더 비활성 (카메라 단독 동작)")

    # ── lgpio polling (Pi 4 신 커널 호환) ─────────────────────
    def _try_lgpio(self) -> bool:
        try:
            import lgpio
            h = lgpio.gpiochip_open(0)
            lgpio.gpio_claim_input(h, RADAR_PIN, lgpio.SET_PULL_UP)
            self._handle = h
            self._lgpio_mod = lgpio
            self._enabled = True
            # 별도 폴링 쓰레드로 RISING edge 감지
            t = threading.Thread(target=self._lgpio_poll, daemon=True)
            t.start()
            logger.info(f"RCWL-0516 활성화 via lgpio polling (GPIO{RADAR_PIN})")
            return True
        except Exception as e:
            logger.debug(f"lgpio 실패: {e}")
            return False

    def _lgpio_poll(self):
        lgpio = self._lgpio_mod
        prev = lgpio.gpio_read(self._handle, RADAR_PIN)
        while self._enabled:
            v = lgpio.gpio_read(self._handle, RADAR_PIN)
            if v == 1 and prev == 0:
                logger.info(f"RCWL-0516 감지 (GPIO{RADAR_PIN})")
                self._last_ts = time.time()
                self._event.set()
            prev = v
            time.sleep(0.05)

    # ── RPi.GPIO 폴백 ──────────────────────────────────────────
    def _try_rpigpio(self) -> bool:
        try:
            import RPi.GPIO as GPIO
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            GPIO.setup(RADAR_PIN, GPIO.IN)
            GPIO.add_event_detect(RADAR_PIN, GPIO.RISING,
                                  callback=self._rpigpio_cb, bouncetime=300)
            self._rpigpio_mod = GPIO
            self._enabled = True
            logger.info(f"RCWL-0516 활성화 via RPi.GPIO (GPIO{RADAR_PIN})")
            return True
        except Exception as e:
            logger.debug(f"RPi.GPIO 실패: {e}")
            try:
                import RPi.GPIO as GPIO
                GPIO.cleanup()
            except Exception:
                pass
            return False

    def _rpigpio_cb(self, channel):
        logger.debug(f"RCWL-0516 감지 RPi.GPIO (GPIO{channel})")
        self._last_ts = time.time()
        self._event.set()

    def wait(self, timeout) -> bool:
        if not self._enabled:
            time.sleep(timeout)
            return False
        triggered = self._event.wait(timeout=timeout)
        self._event.clear()
        return triggered

    def is_active(self) -> bool:
        return (time.time() - self._last_ts) < RADAR_HOLDTIME

    def cleanup(self):
        if self._handle is not None:
            try:
                self._lgpio_mod.gpiochip_close(self._handle)
            except Exception:
                pass
        elif self._enabled:
            try:
                self._rpigpio_mod.cleanup()
            except Exception:
                pass


class KeyboardRadarSource(RadarSource):
    def __init__(self):
        self._event = threading.Event()
        self._last_ts = 0.0

    def start(self):
        t = threading.Thread(target=self._read_loop, daemon=True)
        t.start()
        logger.info("키보드 레이더 소스 활성화 ('r' 입력으로 트리거)")

    def _read_loop(self):
        while True:
            try:
                ch = sys.stdin.read(1)
                if ch == "r":
                    self._last_ts = time.time()
                    self._event.set()
            except Exception:
                time.sleep(0.1)

    def wait(self, timeout) -> bool:
        triggered = self._event.wait(timeout=timeout)
        self._event.clear()
        return triggered

    def is_active(self) -> bool:
        return (time.time() - self._last_ts) < RADAR_HOLDTIME


class FileRadarSource(RadarSource):
    def __init__(self):
        self._last_mtime = 0.0
        self._last_ts = 0.0

    def start(self):
        logger.info(f"파일 레이더 소스 활성화 ({RADAR_MOCK_FILE})")

    def wait(self, timeout) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                mtime = os.path.getmtime(RADAR_MOCK_FILE)
                if mtime != self._last_mtime:
                    self._last_mtime = mtime
                    self._last_ts = time.time()
                    return True
            except FileNotFoundError:
                pass
            time.sleep(0.2)
        return False

    def is_active(self) -> bool:
        return (time.time() - self._last_ts) < RADAR_HOLDTIME


class DisabledRadarSource(RadarSource):
    def wait(self, timeout) -> bool:
        time.sleep(timeout)
        return False


def make_radar_source() -> RadarSource:
    if RADAR_SOURCE == "gpio":
        return GpioRadarSource()
    elif RADAR_SOURCE == "keyboard":
        return KeyboardRadarSource()
    elif RADAR_SOURCE == "file":
        return FileRadarSource()
    else:
        return DisabledRadarSource()

# ── Phase 2B: CaptureSource 추상화 ────────────────────────────
class CaptureSource:
    def read(self) -> object:  # np.ndarray or None
        return None
    def cleanup(self): pass


class FfmpegRtspSource(CaptureSource):
    def __init__(self):
        self._cap = None

    def _open(self):
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        if cap.isOpened():
            self._cap = cap
            logger.info(f"RTSP 연결 성공: {rtsp_url}")
        else:
            logger.warning(f"RTSP 연결 실패: {rtsp_url}")
            self._cap = None

    def read(self):
        if self._cap is None or not self._cap.isOpened():
            self._open()
            if self._cap is None:
                time.sleep(3)
                return None
        # 버퍼 비우기 — 최신 프레임 grab
        for _ in range(3):
            self._cap.grab()
        ret, frame = self._cap.retrieve()
        if not ret:
            logger.warning("RTSP 프레임 읽기 실패 - 재연결")
            self._cap.release()
            self._cap = None
            return None
        return frame

    def cleanup(self):
        if self._cap:
            self._cap.release()


class VideoFileSource(CaptureSource):
    def __init__(self):
        self._cap = None

    def _open(self):
        self._cap = cv2.VideoCapture(CV_SOURCE_PATH)

    def read(self):
        if self._cap is None:
            self._open()
        ret, frame = self._cap.read()
        if not ret:
            self._cap.release()
            self._open()
            ret, frame = self._cap.read()
        return frame if ret else None

    def cleanup(self):
        if self._cap:
            self._cap.release()


class NullCaptureSource(CaptureSource):
    """CAMERA_ENABLED=false 일 때 RTSP 연결 없이 None 반환"""
    pass


class ImageFileSource(CaptureSource):
    def read(self):
        img = cv2.imread(CV_SOURCE_PATH)
        if img is None:
            logger.warning(f"이미지 로딩 실패: {CV_SOURCE_PATH}")
        return img


def make_capture_source() -> CaptureSource:
    if not CAMERA_ENABLED:
        logger.info("CAMERA_ENABLED=false — RTSP 연결 생략")
        return NullCaptureSource()
    if CV_SOURCE == "ffmpeg":
        return FfmpegRtspSource()
    elif CV_SOURCE == "video":
        return VideoFileSource()
    elif CV_SOURCE == "image":
        return ImageFileSource()
    else:
        return FfmpegRtspSource()


# ── Phase 2C: MJPEG 디버그 스트림 ─────────────────────────────
class _DebugHandler(BaseHTTPRequestHandler):
    state: AppState = None

    def do_GET(self):
        if self.path == "/stream":
            self._stream()
        elif self.path == "/stream_raw":
            self._stream_raw()
        elif self.path == "/state.json":
            self._state_json()
        else:
            self._index()

    def do_POST(self):
        if self.path == "/set_mode":
            self._set_mode()
        elif self.path == "/stream_toggle":
            self._stream_toggle()
        else:
            self.send_response(404)
            self.end_headers()

    def _stream_toggle(self):
        self.state.stream_enabled = not self.state.stream_enabled
        body = _json.dumps({"stream_enabled": self.state.stream_enabled}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _set_mode(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            data = _json.loads(body)
            mode = data.get("mode", "")
        except Exception:
            mode = ""

        valid = {"camera", "radar", "both"}
        if mode not in valid:
            resp = _json.dumps({"ok": False, "error": "invalid mode"}).encode()
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(resp)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(resp)
            return

        self.state.active_mode = mode

        if mode == "camera":
            # stop radar_ctl, keep cv2_ffmpeg sending
            subprocess.Popen(
                ["sudo", "systemctl", "stop", "radar_ctl"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        elif mode == "radar":
            # cv2_ffmpeg keeps running but skips sends; start radar_ctl
            subprocess.Popen(
                ["bash", "-c", "sleep 1 && sudo systemctl start radar_ctl"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        elif mode == "both":
            # both services active and sending
            subprocess.Popen(
                ["bash", "-c", "sleep 1 && sudo systemctl start radar_ctl"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )

        resp = _json.dumps({"ok": True, "mode": mode}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(resp)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(resp)

    def _send_mjpeg_frame(self, frame):
        _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n")

    def _stream(self):
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.end_headers()
        while True:
            if not self.state.stream_enabled:
                time.sleep(0.2)
                continue
            frame = self.state.last_frame_annotated
            if frame is None:
                time.sleep(0.05)
                continue
            try:
                self._send_mjpeg_frame(frame)
            except Exception:
                break
            time.sleep(0.05)

    def _stream_raw(self):
        self.send_response(200)
        self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
        self.end_headers()
        last_sent = None
        while True:
            frame = self.state.last_frame_raw
            if frame is None or frame is last_sent:
                time.sleep(1 / 30)
                continue
            last_sent = frame
            try:
                self._send_mjpeg_frame(frame)
            except Exception:
                break
            time.sleep(1 / 30)

    def _state_json(self):
        s = self.state
        radar_active = (time.time() - s.last_radar_ts) < RADAR_HOLDTIME
        body = _json.dumps({
            "count": s.committed_count,
            "previous_count": s.previous_count,
            "radar_active": radar_active,
            "radar_history": list(s.radar_history)[-10:],
            "fps": round(s.fps_ewma, 1),
            "source": s.source,
            "last_inference_ms": round(s.last_inference_ms, 1),
            "sensor_mode": SENSOR_MODE,
            "fusion_mode": FUSION_MODE,
            "env": ENV_TYPE,
            "active_mode": s.active_mode,
            "stream_enabled": s.stream_enabled,
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _index(self):
        html = """<!DOCTYPE html>
<html><head><title>CV Debug Stream</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d0d0d;color:#e0e0e0;font-family:'Courier New',monospace;height:100vh;display:flex;flex-direction:column}
header{padding:8px 14px;background:#1a1a2e;border-bottom:1px solid #333;font-size:13px;display:flex;align-items:center;gap:16px}
header span{color:#7ec8e3}
.main{display:flex;flex:1;gap:0;overflow:hidden}
.panel{display:flex;flex-direction:column;padding:8px;gap:6px}
.panel.cam{flex:2}
.panel.right{flex:1;border-left:1px solid #222}
.label{font-size:10px;color:#666;text-transform:uppercase;letter-spacing:1px;margin-bottom:2px}
img.stream{width:100%;border:1px solid #2a2a3a;display:block}
pre{background:#111;border:1px solid #222;padding:8px;font-size:11px;overflow:auto;flex:1;line-height:1.5}
#s{background:#111;border:1px solid #222;padding:8px;font-size:12px;overflow:auto;flex:1}
.row{display:flex;justify-content:space-between;padding:4px 6px;border-bottom:1px solid #1e1e1e}
.row:hover{background:#1a1a2e}
.k{color:#7ec8e3;min-width:100px}
.v{color:#e0e0e0;text-align:right}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px}
.gauge-wrap{padding:12px 8px}
.gauge-label{font-size:11px;color:#666;text-transform:uppercase;letter-spacing:1px;margin-bottom:8px}
.gauge-count{font-size:56px;font-weight:bold;text-align:center;line-height:1;margin-bottom:10px;color:#7ec8e3}
.gauge-bar-bg{background:#1e1e2e;border-radius:6px;height:18px;overflow:hidden;margin-bottom:4px}
.gauge-bar{height:100%;border-radius:6px;transition:width .3s,background .3s}
.gauge-slots{display:flex;gap:6px;margin-top:10px;flex-wrap:wrap;justify-content:center}
.slot{width:36px;height:36px;border-radius:4px;border:2px solid #333;transition:background .2s,border-color .2s}
.slot.on{background:#e74c3c;border-color:#e74c3c}
.radar-badge{text-align:center;padding:6px;border-radius:6px;font-size:12px;font-weight:bold;margin-top:8px;transition:background .3s}
.radar-on{background:#4a0000;color:#ff6b6b}
.radar-off{background:#1a1a1a;color:#555}
.mode-btn{padding:4px 10px;border:1px solid #444;background:#1a1a2e;color:#e0e0e0;border-radius:4px;cursor:pointer;font-size:11px}
.mode-btn.active{background:#7ec8e3;color:#000;border-color:#7ec8e3}
.stream-btn{padding:4px 10px;border:1px solid #555;background:#2a1a1a;color:#e0a0a0;border-radius:4px;cursor:pointer;font-size:11px}
.stream-btn.on{background:#1a2a1a;color:#a0e0a0;border-color:#555}
</style></head>
<body>
<header>
  <b>CV Debug</b>
  <span id=hdr>connecting...</span>
  <span style="margin-left:auto;display:flex;gap:6px">
    <button class=mode-btn id=btn-camera onclick="setMode('camera')">&#128247; 카메라</button>
    <button class=mode-btn id=btn-radar onclick="setMode('radar')">&#128225; 레이더</button>
    <button class=mode-btn id=btn-both onclick="setMode('both')">&#128256; 둘다</button>
    <button class="stream-btn" id=btn-stream onclick="toggleStream()">&#9654; 스트림</button>
  </span>
</header>
<div class=main>
  <div class="panel cam">
    <div class=label>YOLO Overlay</div>
    <img class=stream src=/stream>
  </div>
  <div class="panel cam">
    <div class=label>Raw (30fps)</div>
    <img class=stream src=/stream_raw>
  </div>
  <div class="panel right">
    <div class=gauge-wrap>
      <div class=gauge-label>재실 인원</div>
      <div class=gauge-count id=gc>-</div>
      <div class=gauge-bar-bg><div class=gauge-bar id=gb style="width:0%"></div></div>
      <div class=gauge-slots id=gs></div>
      <div class=radar-badge id=rb>레이더 -</div>
    </div>
    <div class=label style="margin-top:4px">State</div>
    <div id=s>loading...</div>
  </div>
</div>
<script>
const MAX_SLOTS=10;
const SRC={fusion:'융합',camera:'카메라',radar:'레이더','':`-`};
const MODE={camera:'카메라만',radar:'센서만',both:'카메라+센서'};
const FMODE={gating:'게이팅',confirm:'확인 대기'};
function setMode(m){
  fetch('/set_mode',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({mode:m})})
    .then(r=>r.json()).then(d=>{if(d.ok)updateModeBtns(m);}).catch(()=>{});
}
function updateModeBtns(m){
  ['camera','radar','both'].forEach(k=>{
    const b=document.getElementById('btn-'+k);
    if(b)b.className='mode-btn'+(k===m?' active':'');
  });
}
function toggleStream(){
  fetch('/stream_toggle',{method:'POST'}).then(r=>r.json()).then(d=>{
    const btn=document.getElementById('btn-stream');
    const img=document.querySelector('img.stream');
    if(d.stream_enabled){
      btn.textContent='▶ 스트림';btn.className='stream-btn on';
      img.src='/stream?t='+Date.now();
    } else {
      btn.textContent='■ 종료됨';btn.className='stream-btn';
      img.src='';
    }
  }).catch(()=>{});
}
function fmt(d){
  if(d.active_mode)updateModeBtns(d.active_mode);
  const btn=document.getElementById('btn-stream');
  if(btn){
    btn.textContent=d.stream_enabled?'▶ 스트림':'■ 종료됨';
    btn.className='stream-btn'+(d.stream_enabled?' on':'');
  }
  const radar=d.radar_active;
  const cnt=d.count||0;
  document.getElementById('hdr').innerHTML=
    `<span class=dot style="background:${radar?'#e74c3c':'#555'}"></span>`+
    `감지 인원 <b>${cnt}명</b> &nbsp;|&nbsp; fps ${d.fps} &nbsp;|&nbsp; `+
    `${MODE[d.sensor_mode]||d.sensor_mode}`;

  // 숫자 게이지
  document.getElementById('gc').textContent=cnt+'명';
  const pct=Math.min(100,cnt/MAX_SLOTS*100);
  const bar=document.getElementById('gb');
  bar.style.width=pct+'%';
  bar.style.background=cnt===0?'#2a2a3a':cnt<5?'#2ecc71':cnt<8?'#f39c12':'#e74c3c';

  // 슬롯 표시
  let slots='';
  for(let i=0;i<MAX_SLOTS;i++)
    slots+=`<div class="slot${i<cnt?' on':''}"></div>`;
  document.getElementById('gs').innerHTML=slots;

  // 레이더 배지
  const rb=document.getElementById('rb');
  rb.textContent=radar?'🔴 레이더 감지 중':'⚫ 레이더 대기';
  rb.className='radar-badge '+(radar?'radar-on':'radar-off');

  const ts=d.radar_history.map(t=>new Date(t*1000).toTimeString().slice(0,8));
  const now=new Date().toTimeString().slice(0,8);
  const rows=[
    ['갱신 시각', now],
    ['이전 인원', `${d.previous_count} 명`],
    ['레이더 이력', ts.slice(-3).reverse().join(' / ')||'-'],
    ['초당 프레임', `${d.fps} fps`],
    ['추론 시간', `${d.last_inference_ms} ms`],
    ['카운트 출처', SRC[d.source]||d.source],
    ['센서 모드', MODE[d.sensor_mode]||d.sensor_mode],
    ['융합 모드', FMODE[d.fusion_mode]||d.fusion_mode],
    ['환경', d.env],
  ];
  document.getElementById('s').innerHTML=rows.map(([k,v])=>
    `<div class=row><span class=k>${k}</span><span class=v>${v}</span></div>`
  ).join('');
}
setInterval(()=>fetch('/state.json').then(r=>r.json()).then(fmt).catch(()=>{}),150);
</script>
</body></html>"""
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a): pass


def start_debug_server(state: AppState, port: int):
    handler = type("H", (_DebugHandler,), {"state": state})
    srv = ThreadingHTTPServer(("", port), handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    logger.info(f"디버그 스트림: http://localhost:{port}")

# ── 캡처 전용 스레드 (30fps raw 버퍼) ────────────────────────
def start_capture_thread(cap_src: CaptureSource, state: AppState):
    def worker():
        while True:
            frame = cap_src.read()
            if frame is not None:
                state.last_frame_raw = frame
    threading.Thread(target=worker, daemon=True).start()

# 교통약자 관련 감지 클래스 (모델 교체 시 여기만 수정)
MOBILITY_AID_CLASSES = {
    "wheelchair", "crutch", "crutches", "stroller", "baby carriage",
    "walking frame", "walker", "mobility aid", "cast", "splint",
}
MOBILITY_LABEL_KR = {
    "wheelchair": "휠체어",
    "crutch": "목발", "crutches": "목발",
    "stroller": "유모차", "baby carriage": "유모차",
    "walking frame": "보행기", "walker": "보행기",
    "cast": "기부스", "splint": "기부스",
    "mobility aid": "교통약자",
}

INFER_WIDTH = int(os.getenv("INFER_WIDTH", "416"))

def infer_once(frame, state: AppState):
    t0 = time.time()
    h, w = frame.shape[:2]
    scale = 1.0
    if w > INFER_WIDTH:
        scale = INFER_WIDTH / w
        frame_resized = cv2.resize(frame, (INFER_WIDTH, int(h * scale)))
    else:
        frame_resized = frame

    # ── 메인 모델: 인원 감지 (person class 0) ──────────────────
    results = model.predict(frame_resized, conf=0.4, imgsz=INFER_WIDTH, verbose=False)
    elapsed = time.time() - t0
    state.fps_ewma = 0.1 * (1.0 / elapsed if elapsed > 0 else 0.0) + 0.9 * state.fps_ewma
    state.last_inference_ms = elapsed * 1000

    boxes = []
    for box in results[0].boxes.data:
        x1, y1, x2, y2, conf, cls_id = box.tolist()
        x1, y1, x2, y2 = map(int, (x1, y1, x2, y2))
        if scale < 1.0:
            x1, y1, x2, y2 = int(x1 / scale), int(y1 / scale), int(x2 / scale), int(y2 / scale)
        # person(0) 필터
        if int(cls_id) != 0:
            continue
        bw, bh = x2 - x1, y2 - y1
        if bw < 10 or bh < 20:
            continue
        if bh / bw < 0.2 or bh / bw > 4.0:
            continue
        boxes.append((x1, y1, x2, y2))

    # ultralytics 내장 plot() 으로 오버레이 생성
    annotated = results[0].plot()
    if scale < 1.0:
        annotated = cv2.resize(annotated, (w, h))

    # ── 교통약자 모델: N프레임마다 1회 추론 ─────────────────────
    global _mobility_frame_counter, _last_mobility_found
    _mobility_frame_counter += 1
    if _mobility_frame_counter >= MOBILITY_INFER_INTERVAL:
        _mobility_frame_counter = 0
        mob_model = mobility_model if mobility_model is not None else model
        mob_names = mob_model.names
        mob_classes = {0: "휠체어", 1: "목발"} if mobility_model is not None else None

        mob_results = mob_model.predict(frame_resized, conf=0.45, imgsz=INFER_WIDTH, verbose=False)
        found = []
        for box in mob_results[0].boxes.data:
            x1, y1, x2, y2, conf, cls_id = box.tolist()
            cls_id = int(cls_id)
            if mobility_model is not None:
                kr = mob_classes.get(cls_id)
            else:
                class_name = mob_names.get(cls_id, "").lower()
                kr = MOBILITY_LABEL_KR.get(class_name) if class_name in MOBILITY_AID_CLASSES else None
            if kr and kr not in found:
                if not MOBILITY_ALLOWED_CLASSES or kr in MOBILITY_ALLOWED_CLASSES:
                    found.append(kr)
        _last_mobility_found = found
        if found:
            logger.info(f"[교통약자 감지] {found}")

    logger.info(f"감지된 인원 수: {len(boxes)}")
    return boxes, annotated, _last_mobility_found


def post_update(count: int, radar_active: bool, source_str: str, mobility_classes: list = None):
    if SKIP_SENDS:
        logger.info(f"[SKIP] POST 스킵 count={count} radar={radar_active} src={source_str}")
        return
    try:
        payload = {"count": count}
        if MODE == "debug" and mobility_classes:
            payload["message"] = " ".join(mobility_classes)
            logger.info(f"[DEBUG] 교통약자 LED 출력: {payload['message']}")
        response = requests.post(server_url, json=payload)
        if response.status_code == 200:
            logger.info(f"통합제어보드로 인원 수 전송 성공: {count}")
        else:
            logger.warning(f"통합제어보드 전송 실패: {response.status_code} - {response.text}")
    except Exception as e:
        logger.error(f"통합제어보드 전송 오류: {e}")

# ── Phase 3: FusionCounter ────────────────────────────────────
def decide_count(detected: int, state: AppState, radar_triggered: bool) -> tuple:
    """(count_to_post, source_str) 반환. -1이면 POST 안 함."""
    now = time.time()
    radar_active = (now - state.last_radar_ts) < RADAR_HOLDTIME

    if SENSOR_MODE == "camera":
        return (detected, "camera")

    if SENSOR_MODE == "radar":
        if radar_triggered:
            state.committed_count += 1
        return (state.committed_count, "radar")

    # SENSOR_MODE == "both"
    if FUSION_MODE == "gating":
        return (detected if radar_active else 0, "fusion" if radar_active else "camera")

    # FUSION_MODE == "confirm"
    if radar_triggered:
        state.pending_until = now + CONFIRM_WINDOW
        state.pending_hits = 0
    if now < state.pending_until and detected > 0:
        state.pending_hits += 1
        if state.pending_hits >= CONFIRM_HITS:
            state.committed_count = detected
            state.pending_hits = 0
            state.pending_until = 0.0
            return (state.committed_count, "fusion")
    return (-1, "")

# ── STOMP ─────────────────────────────────────────────────────
async def send_stomp_message(destination, message, max_retries=3):
    if ENV_TYPE == "dev":
        logger.info(f"[SKIP] STOMP 스킵 (dev mode) → {destination}")
        return
    for attempt in range(1, max_retries + 1):
        try:
            async with websocket_connection(primary_url=STOMP_URL, log_context="cv_ffmpeg") as ws:
                await ws.send("CONNECT\naccept-version:1.1,1.2\nhost:localhost\n\n\x00")
                frame = f"SEND\ndestination:{destination}\n\n{json.dumps(message)}\x00"
                await ws.send(frame)
                logger.info(f"STOMP 전송 성공 (시도 {attempt})")
                return
        except Exception as e:
            logger.warning(f"STOMP 전송 실패 (시도 {attempt}/{max_retries}): {e}")
            if attempt < max_retries:
                await asyncio.sleep(2)
            else:
                logger.error("STOMP 전송 최종 실패")

# ── 초기화 ────────────────────────────────────────────────────
state = AppState(stat_people_count=load_stat_count())
last_reset_date = datetime.now().date()

if SENSOR_MODE == "camera":
    radar_src = DisabledRadarSource()
else:
    radar_src = make_radar_source()
    radar_src.start()
RADAR_ENABLED = isinstance(radar_src, GpioRadarSource) and radar_src._enabled

cap_src = make_capture_source()

def handle_exit(sig=None, frame=None):
    radar_src.cleanup()
    cap_src.cleanup()
    save_stat_count(state.stat_people_count)
    sys.exit(0)

signal.signal(signal.SIGINT, handle_exit)
if hasattr(signal, "SIGTERM"):
    signal.signal(signal.SIGTERM, handle_exit)
atexit.register(lambda: save_stat_count(state.stat_people_count))

if ENV_TYPE == "dev":
    start_debug_server(state, DEBUG_STREAM_PORT)

if CAMERA_ENABLED:
    start_capture_thread(cap_src, state)

# ── 메인 루프 ─────────────────────────────────────────────────
while True:
    try:
        # 날짜 리셋
        today = datetime.now().date()
        if today != last_reset_date:
            state.stat_people_count = 0
            last_reset_date = today
            save_stat_count(state.stat_people_count)

        # 레이더 대기 (dev 모드는 논블로킹으로 즉시 통과)
        if ENV_TYPE == "dev":
            radar_triggered = radar_src.wait(timeout=0.05)
        else:
            radar_triggered = radar_src.wait(timeout=RADAR_FALLBACK_INTERVAL)
        if radar_triggered:
            state.last_radar_ts = time.time()
            state.radar_history.append(state.last_radar_ts)
            logger.info("레이더 트리거 → 카메라 추론 시작")
        else:
            logger.debug("레이더 무신호 - 폴링 폴백 추론")

        # 레이더 전용 모드
        if SENSOR_MODE == "radar":
            count, src = decide_count(0, state, radar_triggered)
            if radar_triggered:
                post_update(count, True, src)
                if not SKIP_SENDS:
                    stomp_payload = {
                        "terminal_id": TERMINAL_ID,
                        "people_count": count,
                        "stat_people_count": state.stat_people_count,
                        "file_name": "radar_only",
                    }
                    asyncio.run(send_stomp_message("/api/iot/hid", stomp_payload))
            if RADAR_ENABLED:
                time.sleep(RADAR_HOLDTIME)
            continue

        # 카메라 추론
        if not CAMERA_ENABLED:
            time.sleep(1)
            continue
        frame = state.last_frame_raw
        if frame is None:
            time.sleep(0.1)
            continue

        boxes, annotated, mobility_classes = infer_once(frame, state)

        count, src = decide_count(len(boxes), state, radar_triggered)
        state.source = src if src else state.source

        if ENV_TYPE == "dev":
            state.last_frame_annotated = annotated


        if count >= 0:
            now = time.time()
            was_nonzero = state.previous_count > 0
            if count > state.previous_count:
                state.stat_people_count += count - state.previous_count
            state.previous_count = count
            state.committed_count = count

            # count≥1 또는 count=0 모두 3초마다 POST
            if (now - state.last_post_ts) >= 3.0:
                post_update(count, (now - state.last_radar_ts) < RADAR_HOLDTIME, src, mobility_classes)
                state.last_post_ts = now
                if count >= 1:
                    if SKIP_SENDS:
                        logger.info(f"[SKIP] STOMP 스킵 people={count}")
                    else:
                        stomp_payload = {
                            "terminal_id": TERMINAL_ID,
                            "people_count": count,
                            "stat_people_count": state.stat_people_count,
                            "file_name": "Debug off",
                        }
                        asyncio.run(send_stomp_message("/api/iot/hid", stomp_payload))
                else:
                    logger.info("사람 없음 → 시계 표시 요청")
        else:
            logger.debug("확정 카운트 없음 - POST/STOMP 생략")

    except Exception as e:
        logger.exception(f"루프 오류 - 계속 진행: {e}")

    if ENV_TYPE == "dev":
        pass
    elif not RADAR_ENABLED:
        time.sleep(3)
    else:
        time.sleep(RADAR_HOLDTIME)
