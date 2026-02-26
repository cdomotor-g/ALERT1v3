#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DURATION_SEC="${1:-3600}"
STAMP="$(date +%Y%m%d_%H%M%S)"
SOAK_DIR="$ROOT/rf_log/soak_$STAMP"
mkdir -p "$SOAK_DIR"

EVENTS_JSONL="$SOAK_DIR/rx_events.jsonl"
HOST_JSONL="$SOAK_DIR/host_metrics.jsonl"
REPORT_JSON="$SOAK_DIR/soak_report.json"

# Ensure services are running and pinned to soak paths for this run.
MON_CMD=(python3 "$ROOT/tools/host_monitor.py" --interval 5 --output-jsonl "$HOST_JSONL")
WEB_CMD=(python3 "$ROOT/webui/server.py" --jsonl "$EVENTS_JSONL" --host-metrics-jsonl "$HOST_JSONL" --host 0.0.0.0 --port 8088)

# Receiver process writes to /home/cdomotor/rf_log by design; we'll symlink latest into soak dir at end.
RX_CMD=(python3 "$ROOT/src/ALERT1v3.py")

cleanup(){
  [[ -n "${RX_PID:-}" ]] && kill "$RX_PID" 2>/dev/null || true
  [[ -n "${MON_PID:-}" ]] && kill "$MON_PID" 2>/dev/null || true
  [[ -n "${WEB_PID:-}" ]] && kill "$WEB_PID" 2>/dev/null || true
}
trap cleanup EXIT

: > "$EVENTS_JSONL"

"${MON_CMD[@]}" > "$SOAK_DIR/host_monitor.log" 2>&1 & MON_PID=$!
"${WEB_CMD[@]}" > "$SOAK_DIR/webui.log" 2>&1 & WEB_PID=$!
"${RX_CMD[@]}" > "$SOAK_DIR/receiver.log" 2>&1 & RX_PID=$!

echo "Running soak for ${DURATION_SEC}s..."
sleep "$DURATION_SEC"

# Pull latest receiver events from canonical log path into soak dir.
LATEST_REAL="$(find /home/cdomotor/rf_log -type f -name 'rx_events_*.jsonl' | sort | tail -n1 || true)"
if [[ -n "$LATEST_REAL" && -f "$LATEST_REAL" ]]; then
  cp "$LATEST_REAL" "$EVENTS_JSONL"
fi

python3 "$ROOT/tools/soak_report.py" --events-jsonl "$EVENTS_JSONL" --host-metrics-jsonl "$HOST_JSONL" --out "$REPORT_JSON"

echo "Soak complete: $SOAK_DIR"
cat "$REPORT_JSON"
