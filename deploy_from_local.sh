#!/bin/bash
###############################################################################
# deploy_from_local.sh  (Phase 3 개선)
#
# Local deployment script for SBMS-Pi bus stop devices.
# Run from a machine on the 192.168.10.x network.
#
# 사용법:
#   bash deploy_from_local.sh                     # 전체 배포 (hosts.txt)
#   bash deploy_from_local.sh 10.209.15.58        # 단일 장치
#   bash deploy_from_local.sh --rollback abc1234  # 특정 커밋으로 롤백
#   bash deploy_from_local.sh --check             # 상태 확인만 (배포 없음)
###############################################################################
set -euo pipefail

REPO_URL="https://github.com/softj2019/arch-sbms-pi.git"
BRANCH="prod"
JUMP_HOST="192.168.10.107"
BIND_ADDR="192.168.10.108"
REMOTE_USER="admin"
REMOTE_DIR="/home/admin/gunpo"
DEPLOY_DIR="/home/admin/gunpo/docker"
HOSTS_FILE="$(dirname "${BASH_SOURCE[0]}")/deploy/hosts.txt"

# ── 인자 파싱 ──────────────────────────────────────────────
ROLLBACK_COMMIT=""
CHECK_ONLY=false
EXPLICIT_HOSTS=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --rollback)
            ROLLBACK_COMMIT="$2"
            shift 2
            ;;
        --check)
            CHECK_ONLY=true
            shift
            ;;
        --*)
            echo "알 수 없는 옵션: $1" >&2
            exit 1
            ;;
        *)
            EXPLICIT_HOSTS+=("$1")
            shift
            ;;
    esac
done

# ── 호스트 목록 구성 ────────────────────────────────────────
if [ ${#EXPLICIT_HOSTS[@]} -gt 0 ]; then
    HOSTS=("${EXPLICIT_HOSTS[@]}")
elif [ -f "$HOSTS_FILE" ]; then
    # hosts.txt 에서 읽기 (빈 줄/주석 제외)
    mapfile -t HOSTS < <(grep -v '^\s*#' "$HOSTS_FILE" | grep -v '^\s*$' | awk '{print $1}')
else
    echo "ERROR: deploy/hosts.txt 없음. 단일 IP를 인자로 전달하세요." >&2
    exit 1
fi

# ── 헤더 출력 ───────────────────────────────────────────────
echo "============================================"
if [ -n "$ROLLBACK_COMMIT" ]; then
    echo " SBMS-Pi ROLLBACK → $ROLLBACK_COMMIT"
elif [ "$CHECK_ONLY" = true ]; then
    echo " SBMS-Pi STATUS CHECK ($(date '+%Y-%m-%d %H:%M:%S'))"
else
    echo " SBMS-Pi Deployment ($(date '+%Y-%m-%d %H:%M:%S'))"
fi
echo "============================================"
echo ""

# ── Step 1: 로컬 git 동기화 (배포/롤백 시) ─────────────────
if [ "$CHECK_ONLY" = false ]; then
    echo "[1/4] 로컬 repo 동기화..."
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    cd "$SCRIPT_DIR"

    if [ -d .git ]; then
        git fetch origin "$BRANCH"
        git checkout "$BRANCH"
        if [ -n "$ROLLBACK_COMMIT" ]; then
            git reset --hard "$ROLLBACK_COMMIT"
            echo "  롤백 대상 커밋: $ROLLBACK_COMMIT"
        else
            git reset --hard "origin/$BRANCH"
        fi
    else
        echo "  WARNING: git repo 아님. GitHub에서 직접 클론..."
        cd /tmp
        rm -rf sbms-pi-deploy
        git clone -b "$BRANCH" "$REPO_URL" sbms-pi-deploy
        cd sbms-pi-deploy
    fi

    LOCAL_COMMIT=$(git log --oneline -1)
    echo "  적용 커밋: $LOCAL_COMMIT"
    echo ""
fi

# ── Step 2: 각 장치에 배포 ─────────────────────────────────
if [ "$CHECK_ONLY" = false ]; then
    echo "[2/4] ${#HOSTS[@]}개 장치에 배포 중..."
else
    echo "[1/1] ${#HOSTS[@]}개 장치 상태 확인 중..."
fi
echo ""
echo "HOSTNAME|IP|COMMIT|MAIN_CTL|CV2_FFMPEG|HEALTH|STATUS"
echo "---|---|---|---|---|---|---"

deploy_host() {
    local ip=$1
    local result_file="/tmp/deploy_result_${ip}.txt"

    if [ "$CHECK_ONLY" = true ]; then
        remote_cmd="
HN=\$(hostname)
COMMIT=\$(cd $REMOTE_DIR && git log --oneline -1 2>/dev/null | cut -c1-7 || echo '???')
MAIN_STATUS=\$(systemctl is-active main_ctl 2>/dev/null || echo 'N/A')
CV2_STATUS=\$(systemctl is-active cv2_ffmpeg 2>/dev/null || echo 'N/A')
HEALTH=\$(curl -s --max-time 3 http://localhost:5000/system_info 2>/dev/null | python3 -c 'import sys,json; d=json.load(sys.stdin); print(\"OK\")' 2>/dev/null || echo 'FAIL')
echo \"\$HN|\$ip|\$COMMIT|\$MAIN_STATUS|\$CV2_STATUS|\$HEALTH|CHECK\"
"
    elif [ -n "$ROLLBACK_COMMIT" ]; then
        remote_cmd="
HN=\$(hostname)
cd $REMOTE_DIR
git fetch origin $BRANCH 2>&1 | tail -1
git reset --hard $ROLLBACK_COMMIT 2>&1 | tail -1
COMMIT=\$(git log --oneline -1 | cut -c1-7)
sudo systemctl restart main_ctl 2>/dev/null; sleep 1
MAIN_STATUS=\$(systemctl is-active main_ctl 2>/dev/null || echo 'N/A')
sudo systemctl restart cv2_ffmpeg 2>/dev/null; sleep 2
CV2_STATUS=\$(systemctl is-active cv2_ffmpeg 2>/dev/null || echo 'N/A')
HEALTH=\$(curl -s --max-time 3 http://localhost:5000/system_info 2>/dev/null | python3 -c 'import sys,json; d=json.load(sys.stdin); print(\"OK\")' 2>/dev/null || echo 'FAIL')
echo \"\$HN|\$ip|\$COMMIT|\$MAIN_STATUS|\$CV2_STATUS|\$HEALTH|ROLLBACK\"
"
    else
        remote_cmd="
HN=\$(hostname)
cd $REMOTE_DIR
git fetch origin $BRANCH 2>&1 | tail -1
git reset --hard origin/$BRANCH 2>&1 | tail -1
COMMIT=\$(git log --oneline -1 | cut -c1-7)
sudo systemctl restart main_ctl 2>/dev/null; sleep 1
MAIN_STATUS=\$(systemctl is-active main_ctl 2>/dev/null || echo 'N/A')
sudo systemctl restart cv2_ffmpeg 2>/dev/null; sleep 2
CV2_STATUS=\$(systemctl is-active cv2_ffmpeg 2>/dev/null || echo 'N/A')
HEALTH=\$(curl -s --max-time 3 http://localhost:5000/system_info 2>/dev/null | python3 -c 'import sys,json; d=json.load(sys.stdin); print(\"OK\")' 2>/dev/null || echo 'FAIL')
echo \"\$HN|\$ip|\$COMMIT|\$MAIN_STATUS|\$CV2_STATUS|\$HEALTH|OK\"
"
    fi

    result=$(ssh -o StrictHostKeyChecking=no -o ConnectTimeout=15 -b "$BIND_ADDR" \
        "$REMOTE_USER@$JUMP_HOST" \
        "ssh -o StrictHostKeyChecking=no -o ConnectTimeout=15 -i ~/.ssh/id_ed25519 $REMOTE_USER@$ip '$remote_cmd'" 2>/dev/null)

    if [ -z "$result" ]; then
        echo "???|$ip|???|???|???|???|CONNECT-FAIL" > "$result_file"
    else
        echo "$result" > "$result_file"
    fi
}

# 병렬 배포 (최대 5개 동시)
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

# ── Step 3: 결과 집계 ───────────────────────────────────────
echo ""
SUCCESS=0
FAIL=0
HEALTH_FAIL=0

for ip in "${HOSTS[@]}"; do
    result_file="/tmp/deploy_result_${ip}.txt"
    if [ -f "$result_file" ]; then
        line=$(cat "$result_file")
        echo "$line"
        if echo "$line" | grep -q "CONNECT-FAIL"; then
            FAIL=$((FAIL + 1))
        else
            SUCCESS=$((SUCCESS + 1))
            if echo "$line" | grep -q "HEALTH|FAIL\|FAIL|OK\|FAIL|ROLLBACK"; then
                HEALTH_FAIL=$((HEALTH_FAIL + 1))
            fi
        fi
    else
        echo "???|$ip|???|???|???|???|NO-RESULT"
        FAIL=$((FAIL + 1))
    fi
    rm -f "$result_file"
done

# ── Step 4: 요약 ────────────────────────────────────────────
echo ""
echo "============================================"
echo "[Summary]"
echo "============================================"
echo "  총 장치:    ${#HOSTS[@]}"
echo "  성공:       $SUCCESS"
echo "  연결 실패:  $FAIL"
echo "  Health 이상: $HEALTH_FAIL"
if [ "$CHECK_ONLY" = false ]; then
    echo "  커밋:       ${LOCAL_COMMIT:-N/A}"
fi
echo "  시각:       $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"

if [ "$FAIL" -gt 0 ]; then
    echo ""
    echo "WARNING: $FAIL 개 장치 연결 실패. 재시도:"
    echo "  bash deploy_from_local.sh <ip>"
fi

if [ "$HEALTH_FAIL" -gt 0 ]; then
    echo ""
    echo "WARNING: $HEALTH_FAIL 개 장치 health check 실패."
    echo "  롤백 필요 시: bash deploy_from_local.sh --rollback <COMMIT>"
fi

[ "$FAIL" -eq 0 ]
