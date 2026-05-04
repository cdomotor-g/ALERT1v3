#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_BASE="${FWLAB_LOG_BASE:-$HOME/rf_log}"
LATEST_JSONL="$(find "$LOG_BASE" -type f -name 'rx_events_*.jsonl' 2>/dev/null | sort | tail -n1 || true)"
if [[ -z "${LATEST_JSONL}" ]]; then
  LATEST_JSONL="$ROOT/rf_log/live_placeholder_events.jsonl"
  mkdir -p "$(dirname "$LATEST_JSONL")"
  touch "$LATEST_JSONL"
fi

HOST_JSONL="$(find "$ROOT/rf_log" -type f -name 'host_metrics*.jsonl' 2>/dev/null | sort | tail -n1 || true)"

ARGS=(--jsonl "$LATEST_JSONL" --jsonl-follow-dir "$LOG_BASE" --host 0.0.0.0 --port 8088)
if [[ -n "${HOST_JSONL}" ]]; then
  ARGS+=(--host-metrics-jsonl "$HOST_JSONL")
fi

cd "$ROOT"
export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec python3 -m webui.server "${ARGS[@]}"
