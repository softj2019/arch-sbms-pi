import socket
import requests

def get_ip_address():
    """
    라즈베리파이 보드의 공용(외부) IP 주소를 반환
    :return: 외부 IP 주소 문자열
    """
    try:
        # 외부 IP 확인을 위한 API 요청
        response = requests.get("https://api64.ipify.org?format=json", timeout=5)
        response.raise_for_status()  # HTTP 오류 발생 시 예외 처리
        external_ip = response.json().get("ip", "Unknown")
        return external_ip
    except requests.RequestException as e:
        print(f"Error getting external IP address: {e}")
        return "127.0.0.1"  # 기본값

# 테스트
if __name__ == "__main__":
    print(f"External IP Address: {get_ip_address()}")
