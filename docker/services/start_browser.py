import subprocess
import time
import os
import json
import signal
import psutil
import logging
# 로깅 설정
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# Chromium 메인 프로세스 PIDs
def find_chromium_main_pids():
    main_pids = []
    for process in psutil.process_iter(attrs=['pid', 'name', 'cmdline']):
        try:
            cmd = " ".join(process.info['cmdline']) if process.info['cmdline'] else ""

            # 메인 프로세스 확인 조건
            if process.info['name'] and "chromium" in process.info['name'].lower():
                if "--kiosk" in cmd or "chromium-browser" in cmd or "/usr/lib/chromium/chromium" in cmd:
                    main_pids.append(process.info['pid'])

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return main_pids

# Chromium 메인 프로세스 세이프티 킬
def kill_chromium():
    pids = find_chromium_main_pids()

    if not pids:
        logging.info("kill_chromium: 실행 중인 Chromium 프로세스 없음")
        return False

    logging.info(f"kill_chromium: 종료할 Chromium PIDs: {pids}")

    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            continue

    time.sleep(3)

    pids = find_chromium_main_pids()
    if pids:
        logging.warning(f"kill_chromium: 강제 종료할 Chromium PIDs: {pids}")
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
                logging.info(f"kill_chromium: 강제 종료 완료: PID {pid}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    return True

kill_chromium()


# 2. 기존 Singleton 락 파일 삭제 (충돌 방지)
chromium_profile_dir = os.path.expanduser("~/.chromium-profile")
os.makedirs(chromium_profile_dir, exist_ok=True)
subprocess.run(f"rm -rf {chromium_profile_dir}/Singleton*", shell=True)

# 3. Chromium 기본 설정을 수정하여 번역 기능 완전 비활성화
preferences_file = os.path.join(chromium_profile_dir, "Default", "Preferences")

if not os.path.exists(os.path.dirname(preferences_file)):
    os.makedirs(os.path.dirname(preferences_file))

preferences_data = {
    "translate": {
        "enabled": False,  # 번역 기능 비활성화
        "show_bubble": False  # 번역 창(버블) 비활성화
    },
    "intl": {
        "accept_languages": "ko-KR,ko"  # 한국어만 허용 (자동 번역 조건 제거)
    },
    "profile": {
        "exit_type": "Normal",
        "last_active_time": "0"
    }
}

# 기존 Preferences 파일이 있으면 설정 유지하면서 업데이트
if os.path.exists(preferences_file):
    with open(preferences_file, "r") as f:
        try:
            existing_preferences = json.load(f)
        except json.JSONDecodeError:
            existing_preferences = {}

    existing_preferences.update(preferences_data)

    with open(preferences_file, "w") as f:
        json.dump(existing_preferences, f, indent=4)
else:
    with open(preferences_file, "w") as f:
        json.dump(preferences_data, f, indent=4)

# 4. Chromium 실행 명령어 (Xwayland 강제)
chromium_command = [
    "chromium",
    "--kiosk",
    "--disable-restore-session-state",
    "--window-size=600,800",
    "--force-device-scale-factor=1",
    f"--user-data-dir={chromium_profile_dir}",  # 충돌 방지를 위한 새로운 프로필 경로
    "--disable-gpu",
    "--disable-software-rasterizer",
    "--ozone-platform=x11",
    "--disable-features=TranslateUI,ChromeTranslateUI",  # 번역 UI 비활성화
    "--disable-component-extensions-with-background-pages",  # 기본 내장 번역 확장 비활성화
    "--disable-translate",  # 번역 기능 자체 비활성화
    "--disable-background-networking",  # 자동 업데이트 및 구글 서비스 차단
    "--no-first-run",  # 처음 실행 시 설정 화면 제거
    "--lang=ko",  # 한국어 기본 설정 (불필요한 번역 창 제거)
    '--app="javascript:(function(){ document.body.style.zoom=\'100%\';setTimeout(()=>{ document.body.style.cursor=\'none\'; }, 2000); })()"',
    "http://175.45.215.53/weather"
]

# 5. Chromium 실행 (백그라운드 실행)
subprocess.Popen(" ".join(chromium_command), shell=True)

# 6. 3초 대기 후 커서 숨기기 실행
time.sleep(3)
subprocess.run("echo -e '\x1b[?25l'", shell=True)

# 7. Kiosk 모드 유지 (무한 루프)
while True:
    time.sleep(600)  # 1분 간격 대기
