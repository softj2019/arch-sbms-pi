import tkinter as tk
import subprocess

TRANSFORMS = ["normal", "90", "180", "270"]
LABELS = ["0°", "90°", "180°", "270°"]
OUTPUT = "HDMI-A-1"
FOLLOW_MS = 3000  # 마우스 추적 시간 (ms)

def get_current_transform():
    try:
        result = subprocess.run(["wlr-randr"], capture_output=True, text=True)
        for line in result.stdout.splitlines():
            if "Transform:" in line:
                t = line.strip().split()[-1]
                if t in TRANSFORMS:
                    return TRANSFORMS.index(t)
    except Exception:
        pass
    return 0

def rotate():
    global current_idx
    current_idx = (current_idx + 1) % len(TRANSFORMS)
    transform = TRANSFORMS[current_idx]
    try:
        subprocess.run(
            ["wlr-randr", "--output", OUTPUT, "--transform", transform],
            check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"wlr-randr error: {e}")
    btn.config(text=f"회전\n{LABELS[current_idx]}")

# 마우스 추적 상태
following = False
follow_job = None

def start_follow():
    global following, follow_job
    following = True
    if follow_job:
        root.after_cancel(follow_job)
    follow_job = root.after(FOLLOW_MS, stop_follow)
    track_mouse()

def stop_follow():
    global following
    following = False

def track_mouse():
    if not following:
        return
    mx = root.winfo_pointerx()
    my = root.winfo_pointery()
    x = mx - BTN_W // 2
    y = my - BTN_H // 2
    root.geometry(f"+{x}+{y}")
    root.after(16, track_mouse)  # ~60fps

def on_click(event):
    rotate()
    start_follow()

# 드래그 이동
def start_drag(event):
    global following
    following = False
    root._drag_x = event.x
    root._drag_y = event.y

def do_drag(event):
    x = root.winfo_x() + event.x - root._drag_x
    y = root.winfo_y() + event.y - root._drag_y
    root.geometry(f"+{x}+{y}")

def on_release(event):
    if abs(event.x - root._drag_x) < 5 and abs(event.y - root._drag_y) < 5:
        on_click(event)

current_idx = get_current_transform()

root = tk.Tk()
root.title("화면 회전")
root.overrideredirect(True)
root.attributes("-topmost", True)
root.attributes("-alpha", 0.85)

BTN_W, BTN_H = 80, 80
root.update_idletasks()
sw = root.winfo_screenwidth()
sh = root.winfo_screenheight()
x = sw - BTN_W - 10
y = (sh - BTN_H) // 2
root.geometry(f"{BTN_W}x{BTN_H}+{x}+{y}")

btn = tk.Button(
    root,
    text=f"회전\n{LABELS[current_idx]}",
    bg="#333333",
    fg="white",
    activebackground="#555555",
    activeforeground="white",
    relief="flat",
    font=("sans-serif", 11, "bold"),
    cursor="hand2"
)
btn.pack(fill="both", expand=True)

btn.bind("<ButtonPress-1>", start_drag)
btn.bind("<B1-Motion>", do_drag)
btn.bind("<ButtonRelease-1>", on_release)

root.mainloop()
