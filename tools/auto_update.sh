#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/rf_log/auto_update"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/run_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1

PROFILE="${FWLAB_AUTO_PROFILE:-control}"
PRESET="${FWLAB_AUTO_PRESET:-}"

echo "[auto-update] start profile=$PROFILE preset=${PRESET:-none} root=$ROOT"

cd "$ROOT"
if [[ ! -d .git ]]; then
  echo "[auto-update] ERROR: not a git repo"
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "[auto-update] WARN: repo dirty; skipping auto-update"
  exit 0
fi

CUR="$(git rev-parse HEAD)"
git fetch origin
NEW="$(git rev-parse origin/main)"

echo "[auto-update] current=$CUR origin/main=$NEW"
if [[ "$CUR" == "$NEW" ]]; then
  echo "[auto-update] no changes"
  exit 0
fi

git reset --hard origin/main

CMD=("$ROOT/scripts/install_fwlab.sh" --profile "$PROFILE" --update --yes)
if [[ -n "$PRESET" ]]; then
  CMD+=(--preset "$PRESET")
fi

echo "[auto-update] running: ${CMD[*]}"
"${CMD[@]}"

echo "[auto-update] complete new_head=$(git rev-parse HEAD)"
