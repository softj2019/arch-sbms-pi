import os
import signal
import psutil

def find_chromium_main_pids():
    """Chromium의 메인 프로세스 PIDs를 찾음"""
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

# Chromium 메인 프로세스 세이프 킬
def kill_chromium():
    pids = find_chromium_main_pids()

    if not pids:
        logging.error("kill_chromium: 실행 중인 Chromium 메인 프로세스를 찾을 수 없습니다.")
        return False

    print(f"🔍 종료할 Chromium 메인 PIDs: {pids}")

    # 안전한 종료 (SIGTERM)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)  # 정상 종료 시도
        except (ProcessLookupError, PermissionError):
            continue

    # 강제 종료 (SIGKILL) - 3초 후 여전히 실행 중이면 강제 종료
    for _ in range(3):
        if not find_chromium_main_pids():
            print("kill_chromium: Chromium 정상 종료 완료")
            return True
        os.sleep(1)

    pids = find_chromium_main_pids()
    if pids:
        print(f"⚠️ 강제 종료할 Chromium PIDs: {pids}")
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
                print(f"kill_chromium: 강제 종료 완료: PID {pid}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue

    return True

if __name__ == "__main__":
    kill_chromium()
