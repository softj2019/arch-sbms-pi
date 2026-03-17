import os
def turn_off_display():
    os.system("echo 'standby 0' | cec-client -s -d 1")  # HDMI 전원 OFF

def turn_on_display():
    os.system("echo 'on 0' | cec-client -s -d 1")  # HDMI 전원 ON

def check_power_status():
    os.system("echo 'pow 0' | cec-client -s -d 1")  # 전원 상태 확인

# 테스트 실행
check_power_status()  # 현재 전원 상태 확인
