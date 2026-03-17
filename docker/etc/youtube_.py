import os
from yt_dlp import YoutubeDL

url = "https://www.youtube.com/watch?v=u-6KyqC44js"
output_path = "C:/Users/my/Downloads/downloaded_video.mp4"

ydl_opts = {
    "outtmpl": output_path,
    "format": "mp4"
}

with YoutubeDL(ydl_opts) as ydl:
    ydl.download([url])
print("영상 다운로드 완료:", output_path)
