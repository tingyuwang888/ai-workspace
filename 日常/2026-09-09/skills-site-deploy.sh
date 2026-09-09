#!/bin/bash
# Deploy /skills/ location to tiance.conf on 10.57.80.163
# Idempotent, with rollback on nginx -t failure.
set -e

TS=$(date +%Y%m%d_%H%M%S)
CONF=/etc/nginx/conf.d/tiance.conf
BAK=${CONF}.bak.${TS}
NEW=/tmp/tiance.conf.new.$$

echo "=== Step 1: Backup ==="
sudo cp -a "$CONF" "$BAK"
echo "backup: $BAK"

echo "=== Step 2: Idempotency check ==="
if grep -q 'location \^~ /skills/' "$CONF"; then
    echo "ERROR: /skills/ location already exists in $CONF, aborting"
    exit 1
fi

echo "=== Step 3: Find insertion point ==="
LINE=$(grep -n '^    location ~ \^/ {' "$CONF" | head -1 | cut -d: -f1)
if [ -z "$LINE" ]; then
    echo "ERROR: cannot find '    location ~ ^/ {' line, aborting"
    exit 1
fi
echo "target line: $LINE"

echo "=== Step 4: Build new conf ==="
head -n $((LINE-1)) "$BAK" > "$NEW"
cat >> "$NEW" <<'BLOCK'
    # ===== Skill 发布中心（tdops 维护，2026-09-09 新增）=====
    location ^~ /skills/ {
        alias /data01/td/skills-site/;
        index index.html;
        autoindex off;
        add_header Cache-Control "no-cache";
    }

BLOCK
tail -n +$LINE "$BAK" >> "$NEW"

echo "=== Step 5: Diff preview ==="
diff -u "$BAK" "$NEW" || true

echo "=== Step 6: Apply ==="
sudo cp "$NEW" "$CONF"
rm -f "$NEW"

echo "=== Step 7: nginx -t ==="
if ! sudo nginx -t; then
    echo "!!! nginx -t FAILED, rolling back !!!"
    sudo cp "$BAK" "$CONF"
    sudo nginx -t
    exit 2
fi

echo "=== Step 8: reload ==="
sudo nginx -s reload
sleep 1

echo "=== Step 9: verify ==="
echo "--- HEAD /skills/ ---"
curl -sI http://localhost/skills/ | head -5
echo "--- first 5 lines of body ---"
curl -s http://localhost/skills/ | head -5
echo "--- body size ---"
curl -s http://localhost/skills/ | wc -c

echo "=== DONE ==="
echo "URL: http://10.57.80.163/skills/"
echo "Backup: $BAK"
