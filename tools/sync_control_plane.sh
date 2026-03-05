#!/usr/bin/env bash
set -euo pipefail

# Push selected data-plane artifacts from Pi -> off-prem control-plane node.
# Requires SSH key auth for camadmin@172.105.189.57.

REMOTE_HOST="camadmin@172.105.189.57"
REMOTE_DIR="/home/camadmin/apps/ALERT1v3/rf_log"
SSH_KEY="/home/cdomotor/.ssh/linode_control_ed25519"

if [[ ! -f "$SSH_KEY" ]]; then
  echo "missing ssh key: $SSH_KEY" >&2
  exit 2
fi

SSH_OPTS=(-i "$SSH_KEY" -o IdentitiesOnly=yes -o StrictHostKeyChecking=accept-new)

# Ensure remote destination exists
ssh "${SSH_OPTS[@]}" "$REMOTE_HOST" "mkdir -p '$REMOTE_DIR' '$REMOTE_DIR/archive_state' '$REMOTE_DIR/archive_state/chunks'"

# 1) Push recent rx event logs (last 3 day folders) from /home/cdomotor/rf_log
# shellcheck disable=SC2012
DAY_DIRS=$(ls -1d /home/cdomotor/rf_log/* 2>/dev/null | grep -E '/[0-9]{4}-[0-9]{2}-[0-9]{2}$' | sort | tail -n 3 || true)
for d in $DAY_DIRS; do
  bn=$(basename "$d")
  rsync -az --delete \
    -e "ssh ${SSH_OPTS[*]}" \
    --include 'rx_events_*.jsonl' --exclude '*' \
    "$d/" "$REMOTE_HOST:$REMOTE_DIR/$bn/"
done

# 2) Push archive manifest/chunks from project-local rf_log archive state
LOCAL_ARCHIVE_ROOT="/home/cdomotor/.openclaw/workspace/projects/ALERT1v3/rf_log/archive_state"
if [[ -d "$LOCAL_ARCHIVE_ROOT" ]]; then
  rsync -az \
    -e "ssh ${SSH_OPTS[*]}" \
    "$LOCAL_ARCHIVE_ROOT/" "$REMOTE_HOST:$REMOTE_DIR/archive_state/"
fi

# 3) Keep host metrics for optional control-plane diagnostics
LOCAL_HOST_METRICS="/home/cdomotor/.openclaw/workspace/projects/ALERT1v3/rf_log/host_metrics.jsonl"
if [[ -f "$LOCAL_HOST_METRICS" ]]; then
  rsync -az -e "ssh ${SSH_OPTS[*]}" "$LOCAL_HOST_METRICS" "$REMOTE_HOST:$REMOTE_DIR/host_metrics.jsonl"
fi

echo "sync_control_plane: ok"
