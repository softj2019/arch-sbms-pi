@echo off
REM sola-1 SSH 포워딩 터널 일괄 실행
REM VNC: localhost:5900, 디버그 스트림: localhost:8089

echo [sola-tunnels] 기존 포워딩 프로세스 정리 중...

REM 5900, 8089 포트를 점유한 ssh.exe만 종료
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5900 "  ^| findstr "LISTENING"') do taskkill /PID %%a /F >nul 2>&1
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8089 "  ^| findstr "LISTENING"') do taskkill /PID %%a /F >nul 2>&1

timeout /t 1 /nobreak >nul

echo [sola-tunnels] VNC 터널 시작 (localhost:5900)...
start "" ssh -f -N sola-vnc

echo [sola-tunnels] 디버그 스트림 터널 시작 (localhost:8089)...
start "" ssh -f -N sola-8089

timeout /t 2 /nobreak >nul

echo [sola-tunnels] 포트 상태 확인:
netstat -ano | findstr ":5900 \|:8089 " | findstr "LISTENING"

echo.
echo [sola-tunnels] 완료
echo   VNC:    localhost:5900
echo   Stream: http://localhost:8089
