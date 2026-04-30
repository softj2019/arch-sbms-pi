#!/bin/bash
# main_ctl PID 파일 잠금 문제 복구 스크립트

echo "=== main_ctl 복구 시작 ==="

ssh admin@192.168.10.100 << 'EOF'
echo "1. PID 파일 확인..."
ls -la /tmp/main_ctl.pid 2>/dev/null || echo "   PID 파일 없음"

echo "2. PID 파일 정리..."
rm -f /tmp/main_ctl.pid
echo "   ✓ 삭제됨"

echo "3. 서비스 재시작..."
sudo systemctl restart main_ctl.service
echo "   ✓ 재시작됨"

sleep 2

echo "4. 상태 확인..."
systemctl status main_ctl.service --no-pager | grep -E "Active:|PID|since"

echo "5. radar_ctl 상태 확인..."
systemctl status radar_ctl.service --no-pager | grep -E "Active:|PID|since"
EOF

echo "=== 복구 완료 ==="
