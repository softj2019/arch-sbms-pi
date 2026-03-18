#!/bin/bash
# daily_health_report.py를 cron에 등록 (매일 06:00)
CRON_LINE="0 6 * * * cd /home/admin/gunpo/docker && /home/admin/gunpo/venv/bin/python3 daily_health_report.py >> /home/admin/gunpo/docker/logs/daily_health.log 2>&1"

# 이미 등록되어 있으면 스킵
if crontab -l 2>/dev/null | grep -q "daily_health_report"; then
    echo "already registered"
else
    (crontab -l 2>/dev/null; echo "$CRON_LINE") | crontab -
    echo "cron registered: daily_health_report at 06:00"
fi
