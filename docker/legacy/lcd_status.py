import subprocess

def get_display_status():
    try:
        # 'wlr-randr' 명령 실행 및 출력 가져오기
        result = subprocess.run(["wlr-randr"], capture_output=True, text=True, check=True)
        output = result.stdout.splitlines()

        display_status = {}

        # HDMI 및 기타 디스플레이 정보를 파싱
        current_display = None
        for line in output:
            line = line.strip()
            if line.startswith("HDMI") or line.startswith("DP") or line.startswith("eDP"):
                current_display = line.split(" ")[0]  # 첫 번째 단어가 디스플레이 이름
                display_status[current_display] = {"enabled": None}
            elif "Enabled:" in line and current_display:
                status = line.split(":")[1].strip()
                display_status[current_display]["enabled"] = status.lower() == "yes"

        return display_status

    except subprocess.CalledProcessError as e:
        print(f"Error running wlr-randr: {e}")
        return None

# 디스플레이 상태 확인
if __name__ == "__main__":
    status = get_display_status()
    if status:
        for display, info in status.items():
            print(f"Display: {display}, Power On: {info['enabled']}")
