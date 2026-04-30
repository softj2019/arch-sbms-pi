#!/bin/bash

# Tail sola-1 service logs in real-time
# Usage: ./tail_logs.sh [service] [lines]
# Default: tail -f both main_ctl and radar_ctl (last 20 lines)

SERVICE=${1:-both}
LINES=${2:-20}

case $SERVICE in
  main)
    ssh admin@192.168.10.100 "journalctl -u main_ctl.service -f -n $LINES"
    ;;
  radar)
    ssh admin@192.168.10.100 "journalctl -u radar_ctl.service -f -n $LINES"
    ;;
  cv2)
    ssh admin@192.168.10.100 "journalctl -u cv2_ffmpeg.service -f -n $LINES"
    ;;
  both)
    echo "=== Following main_ctl + radar_ctl (last $LINES lines) ==="
    ssh admin@192.168.10.100 "journalctl -u main_ctl.service -u radar_ctl.service -f -n $LINES"
    ;;
  all)
    echo "=== Following all services (last $LINES lines) ==="
    ssh admin@192.168.10.100 "journalctl -f -n $LINES"
    ;;
  *)
    echo "Usage: $0 [main|radar|cv2|both|all] [lines]"
    echo "  main   - tail main_ctl.service"
    echo "  radar  - tail radar_ctl.service"
    echo "  cv2    - tail cv2_ffmpeg.service"
    echo "  both   - tail main_ctl + radar_ctl (default)"
    echo "  all    - tail all services"
    echo ""
    echo "Example:"
    echo "  $0 main 50      # Last 50 lines of main_ctl"
    echo "  $0 both         # Both services, last 20 lines"
    exit 1
    ;;
esac
