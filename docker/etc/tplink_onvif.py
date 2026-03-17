from onvif import ONVIFCamera
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger()

# TP-Link VIGI 카메라 정보
camera_ip = "192.168.10.110"
port = 2020  # ONVIF 기본 포트
username = "admin"
password = "rlawltjd"

cam = ONVIFCamera('192.168.10.110', 2020, 'admin', 'rlawltjd')

# Get camera service
media = cam.create_media_service()

# Get camera profiles
profiles = media.GetProfiles()

# Use the first profile
token = profiles[0].token

# Get stream URI
stream_setup = {'Stream': 'RTP-Unicast', 'Transport': 'RTSP'}
stream_uri = media.GetStreamUri({'StreamSetup': stream_setup, 'ProfileToken': token})

print(f"RTSP Stream URI: {stream_uri.Uri}")