#!/bin/bash
###############################################################################
# deploy_from_local.sh
#
# Local deployment script for SPMS Raspberry Pi bus stop devices.
# Run this from a machine on the 192.168.10.x network that can reach the
# SSH jump host at 192.168.10.107.
#
# Usage:
#   bash deploy_from_local.sh              # deploy to ALL devices
#   bash deploy_from_local.sh 10.209.15.58 # deploy to a single device
###############################################################################

set -euo pipefail

REPO_URL="https://github.com/softj2019/arch-sbms-pi.git"
BRANCH="prod"
JUMP_HOST="192.168.10.107"
BIND_ADDR="192.168.10.108"
REMOTE_USER="admin"
REMOTE_DIR="/home/admin/gunpo"
DEPLOY_DIR="/home/admin/gunpo/docker"

ALL_HOSTS=(
  10.209.15.58      # 26019 철쭉동산
  10.248.121.141    # 26023 송정마을
  10.16.180.199     # 26030 남천병원
  10.143.243.208    # 26037 문화예술회관
  10.175.183.222    # 26039 문화예술회관
  10.237.252.167    # 26058 13단지아파트입구
  10.135.26.19      # 26063 복합화물터미널후문·가족센터
  10.183.203.184    # 26073 군포국민체육센터
  10.223.71.219     # 26074 군포국민체육센터
  10.37.199.138     # 26082 당동주공아파트
  10.228.31.17      # 26084 당동주공아파트
  10.206.68.246     # 26176 5단지517동앞
  10.47.108.150     # 26200 부곡3단지아파트
  10.167.7.62       # 26201 부곡3단지아파트
  10.146.15.206     # 26225 군포첨단산업단지
  10.137.225.187    # 26227 군포첨단산업단지
  10.6.196.213      # 26238 삼성마을5단지아파트입구
  10.203.242.107    # 26240 신기초등학교정문
  10.47.237.69      # 26243 신기초등학교후문
  10.207.180.137    # 26249 신한애자
  10.118.63.30      # 26257 군포역2번출구
  10.80.110.233     # 26366 산본도서관
  10.232.193.180    # 26399 군포시장
  10.143.174.196    # 26416 송정지구입구
  10.94.103.151     # 26417 송정지구입구
)

# If specific hosts are passed as arguments, use those instead
if [ $# -gt 0 ]; then
  HOSTS=("$@")
else
  HOSTS=("${ALL_HOSTS[@]}")
fi

# --- SSH credential setup (sshpass-free approach) ---
setup_ssh_askpass() {
  export SSH_ASKPASS_REQUIRE=force
  export SSH_ASKPASS=$(mktemp)
  echo '#!/bin/bash' > "$SSH_ASKPASS"
  echo 'echo admin' >> "$SSH_ASKPASS"
  chmod +x "$SSH_ASKPASS"
}

cleanup() {
  rm -f "$SSH_ASKPASS" 2>/dev/null
  # Clean up result files
  rm -f /tmp/deploy_result_*.txt 2>/dev/null
}
trap cleanup EXIT

# --- Step 1: Pull latest prod from GitHub ---
echo "============================================"
echo " SPMS-Pi Deployment ($(date '+%Y-%m-%d %H:%M:%S'))"
echo "============================================"
echo ""
echo "[1/4] Pulling latest '$BRANCH' branch from GitHub..."

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [ -d .git ]; then
  git fetch origin "$BRANCH"
  git checkout "$BRANCH"
  git reset --hard "origin/$BRANCH"
else
  echo "WARNING: Not a git repo. Cloning fresh..."
  cd /tmp
  rm -rf spms-pi-deploy
  git clone -b "$BRANCH" "$REPO_URL" spms-pi-deploy
  cd spms-pi-deploy
fi

LOCAL_COMMIT=$(git log --oneline -1)
echo "Local commit: $LOCAL_COMMIT"
echo ""

# --- Step 2: Deploy to all devices via jump host ---
echo "[2/4] Deploying to ${#HOSTS[@]} devices..."
echo ""
echo "HOSTNAME|IP|COMMIT|MAIN_CTL|CV2_FFMPEG|STATUS"
echo "---|---|---|---|---|---"

setup_ssh_askpass

deploy_host() {
  local ip=$1
  local result_file="/tmp/deploy_result_${ip}.txt"

  result=$(ssh -o StrictHostKeyChecking=no -o ConnectTimeout=15 -b "$BIND_ADDR" \
    "$REMOTE_USER@$JUMP_HOST" \
    "export SSH_ASKPASS_REQUIRE=force; \
     export SSH_ASKPASS=\$(mktemp); \
     echo '#!/bin/bash' > \"\$SSH_ASKPASS\"; \
     echo 'echo admin' >> \"\$SSH_ASKPASS\"; \
     chmod +x \"\$SSH_ASKPASS\"; \
     ssh -o StrictHostKeyChecking=no -o ConnectTimeout=15 $REMOTE_USER@$ip '
HN=\$(hostname)

# --- git pull ---
cd $REMOTE_DIR 2>/dev/null || cd $REMOTE_DIR
git fetch origin $BRANCH 2>&1 | tail -1
git reset --hard origin/$BRANCH 2>&1 | tail -1
COMMIT=\$(git log --oneline -1 | cut -c1-7)

# --- restart main_ctl service ---
sudo systemctl restart main_ctl 2>/dev/null
sleep 1
MAIN_STATUS=\$(systemctl is-active main_ctl 2>/dev/null || echo \"N/A\")

# --- restart cv2_ffmpeg service ---
sudo systemctl restart cv2_ffmpeg 2>/dev/null
sleep 2
CV2_STATUS=\$(systemctl is-active cv2_ffmpeg 2>/dev/null || echo \"N/A\")

echo \"\$HN|\$ip|\$COMMIT|\$MAIN_STATUS|\$CV2_STATUS|OK\"
' 2>/dev/null; rm -f \"\$SSH_ASKPASS\"" 2>/dev/null)

  if [ -z "$result" ]; then
    echo "???|$ip|???|???|???|CONNECT-FAIL" > "$result_file"
  else
    echo "$result" > "$result_file"
  fi
}

# Deploy in parallel (max 5 at a time to avoid overloading jump host)
PARALLEL_MAX=5
running=0

for ip in "${HOSTS[@]}"; do
  deploy_host "$ip" &
  running=$((running + 1))

  if [ "$running" -ge "$PARALLEL_MAX" ]; then
    wait -n 2>/dev/null || wait
    running=$((running - 1))
  fi
done
wait

# --- Step 3: Collect and display results ---
echo ""
SUCCESS=0
FAIL=0

for ip in "${HOSTS[@]}"; do
  result_file="/tmp/deploy_result_${ip}.txt"
  if [ -f "$result_file" ]; then
    line=$(cat "$result_file")
    echo "$line"
    if echo "$line" | grep -q "CONNECT-FAIL"; then
      FAIL=$((FAIL + 1))
    else
      SUCCESS=$((SUCCESS + 1))
    fi
  else
    echo "???|$ip|???|???|???|NO-RESULT"
    FAIL=$((FAIL + 1))
  fi
done

# --- Step 4: Summary ---
echo ""
echo "============================================"
echo "[4/4] Deployment Summary"
echo "============================================"
echo "  Total devices:  ${#HOSTS[@]}"
echo "  Success:        $SUCCESS"
echo "  Failed:         $FAIL"
echo "  Local commit:   $LOCAL_COMMIT"
echo "  Timestamp:      $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"

if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo "WARNING: $FAIL device(s) failed. Re-run for specific IPs:"
  echo "  bash deploy_from_local.sh <ip1> <ip2> ..."
  exit 1
fi

echo ""
echo "All devices deployed successfully."
exit 0
