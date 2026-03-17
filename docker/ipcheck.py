import requests

services = [
    "https://api64.ipify.org?format=json",
    "https://ifconfig.me/ip",
    "https://checkip.amazonaws.com",
    "https://api.myip.com"
]

for service in services:
    try:
        response = requests.get(service, timeout=5)
        print(f"{service}: {response.text.strip()}")
    except requests.RequestException:
        print(f"⛔ {service} 연결 실패")
