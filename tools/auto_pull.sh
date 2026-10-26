#!/usr/bin/env bash
# /opt/big-e-inventory/tools/auto_pull.sh
# Automatically pulls the latest commits from GitHub repository and reloads big-e-inventory.service if updated.

set -euo pipefail

APP_DIR="/opt/big-e-inventory"
cd "$APP_DIR"

# 1. Fetch latest main
git fetch origin main --quiet 2>/dev/null || exit 0

LOCAL_HASH=$(git rev-parse HEAD 2>/dev/null || echo "none")
REMOTE_HASH=$(git rev-parse origin/main 2>/dev/null || echo "none")

if [ "$LOCAL_HASH" = "$REMOTE_HASH" ] || [ "$REMOTE_HASH" = "none" ]; then
    # Already up to date
    exit 0
fi

echo "[Big-E-Inventory Auto-Update] $(date '+%Y-%m-%d %H:%M:%S') New commit detected ($LOCAL_HASH -> $REMOTE_HASH)"

# 2. Hard reset to origin/main (preserving untracked runtime .env and data/)
git reset --hard origin/main

# 3. Check if dependencies changed
if git diff --name-only "$LOCAL_HASH" "$REMOTE_HASH" | grep -E -q "^(requirements.txt|pyproject.toml)"; then
    echo "[Big-E-Inventory Auto-Update] Dependencies changed. Updating environment..."
    if command -v uv >/dev/null 2>&1; then
        uv pip install -r requirements.txt --quiet || true
    else
        "$APP_DIR/.venv/bin/pip" install -r requirements.txt --quiet || true
    fi
fi

# 4. Check if systemd service definition changed
if git diff --name-only "$LOCAL_HASH" "$REMOTE_HASH" | grep -q "^tools/big-e-inventory.service"; then
    echo "[Big-E-Inventory Auto-Update] Updating systemd service definition..."
    sudo cp "$APP_DIR/tools/big-e-inventory.service" /etc/systemd/system/big-e-inventory.service
    sudo systemctl daemon-reload
fi

# 5. Restart big-e-inventory.service
echo "[Big-E-Inventory Auto-Update] Restarting big-e-inventory.service..."
sudo systemctl restart big-e-inventory.service

echo "[Big-E-Inventory Auto-Update] Successfully deployed commit $REMOTE_HASH"
