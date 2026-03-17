#!/bin/bash
# Phase 5: 전체 25대 Pi에 prod 브랜치 배포 + main_ctl 재시작
export SSH_ASKPASS_REQUIRE=force
export SSH_ASKPASS=$(mktemp)
echo '#!/bin/bash' > "$SSH_ASKPASS"
echo 'echo admin' >> "$SSH_ASKPASS"
chmod +x "$SSH_ASKPASS"

HOSTS="10.209.15.58 10.248.121.141 10.16.180.199 10.135.235.129 10.175.183.222 10.237.252.167 10.135.26.19 10.183.203.184 10.223.71.219 10.37.199.138 10.228.31.17 10.206.68.246 10.47.108.150 10.185.74.120 10.146.15.206 10.137.225.187 10.72.219.36 10.248.147.144 10.47.237.69 10.207.180.137 10.203.78.114 10.80.110.233 10.232.193.180 10.143.174.196 10.94.103.151"

SUCCESS=0
FAIL=0

deploy_host() {
    local ip=$1
    result=$(ssh -o StrictHostKeyChecking=no -o ConnectTimeout=8 admin@192.168.10.107 \
        "export SSH_ASKPASS_REQUIRE=force; export SSH_ASKPASS=\$(mktemp); echo '#!/bin/bash' > \"\$SSH_ASKPASS\"; echo 'echo admin' >> \"\$SSH_ASKPASS\"; chmod +x \"\$SSH_ASKPASS\"; ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 admin@$ip '
        HN=\$(hostname)
        cd /home/admin/gunpo
        git fetch origin prod 2>&1 | tail -1
        git checkout prod 2>/dev/null
        git reset --hard origin/prod 2>&1 | tail -1
        COMMIT=\$(git log --oneline -1)
        sudo systemctl restart main_ctl
        sleep 3
        STATUS=\$(systemctl is-active main_ctl)
        echo \"\$HN|\$COMMIT|\$STATUS\"
    '" 2>/dev/null)

    if [ -z "$result" ]; then
        echo "FAIL|$ip|UNREACHABLE"
    else
        echo "$result"
    fi
}

echo "===== Phase 5 전체 배포 시작 ====="
echo ""

for ip in $HOSTS; do
    deploy_host "$ip" &
done

wait
rm -f "$SSH_ASKPASS"
echo ""
echo "===== 배포 완료 ====="
