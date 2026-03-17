LED 제어 라이브러리 설치
git clone https://github.com/hzeller/rpi-rgb-led-matrix.git
cd rpi-rgb-led-matrix
sudo apt-get install libgraphicsmagick++-dev libwebp-dev -y
make build-python

sudo python3 examples-api-use/scrolling-text-example.py --led-rows=32 --led-cols=32 --led-slowdown-gpio=2

웹을 통해 텍스트를 입력하고 이를 LED 스크린에 표시할 수 있는 Flask 기반 웹 서버를 구현
sudo pip3 install flask


python3 -m venv venv
source venv/bin/activate
deactivate

curl -i -N -H "Connection: Upgrade" \
-H "Upgrade: websocket" \
-H "Host: localhost:8080" \
-H "Origin: http://10.0.0.145:8099" \
-H "Sec-WebSocket-Version: 13" \
-H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
http://10.0.0.145:8099/websocket