#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_BASE="${LOG_BASE:-$ROOT/rf_log}"
EVENTS_JSONL="${EVENTS_JSONL:-}"
HOST_METRICS_JSONL="${HOST_METRICS_JSONL:-$LOG_BASE/host_metrics.jsonl}"
WEB_HOST="${WEB_HOST:-127.0.0.1}"
WEB_PORT="${WEB_PORT:-8088}"
MON_INTERVAL="${MON_INTERVAL:-5}"

mkdir -p "$LOG_BASE"

if [[ -z "$EVENTS_JSONL" ]]; then
  EVENTS_JSONL="$LOG_BASE/latest_rx_events.jsonl"
  touch "$EVENTS_JSONL"
fi

echo "[fw-lab] host monitor -> $HOST_METRICS_JSONL"
python3 "$ROOT/tools/host_monitor.py" --interval "$MON_INTERVAL" --output-jsonl "$HOST_METRICS_JSONL" &
MON_PID=$!

echo "[fw-lab] web ui -> http://$WEB_HOST:$WEB_PORT"
python3 "$ROOT/webui/server.py" --jsonl "$EVENTS_JSONL" --host-metrics-jsonl "$HOST_METRICS_JSONL" --host "$WEB_HOST" --port "$WEB_PORT" &
WEB_PID=$!

cleanup() {
  kill "$MON_PID" 2>/dev/null || true
  kill "$WEB_PID" 2>/dev/null || true
}
trap cleanup EXIT

wait "$WEB_PID"
