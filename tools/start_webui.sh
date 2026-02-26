#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LATEST_JSONL="$(find /home/cdomotor/rf_log -type f -name 'rx_events_*.jsonl' 2>/dev/null | sort | tail -n1 || true)"
if [[ -z "${LATEST_JSONL}" ]]; then
  LATEST_JSONL="$ROOT/rf_log/live_placeholder_events.jsonl"
  mkdir -p "$(dirname "$LATEST_JSONL")"
  touch "$LATEST_JSONL"
fi

HOST_JSONL="$(find "$ROOT/rf_log" -type f -name 'host_metrics*.jsonl' 2>/dev/null | sort | tail -n1 || true)"

ARGS=(--jsonl "$LATEST_JSONL" --jsonl-follow-dir "/home/cdomotor/rf_log" --host 0.0.0.0 --port 8088)
if [[ -n "${HOST_JSONL}" ]]; then
  ARGS+=(--host-metrics-jsonl "$HOST_JSONL")
fi

exec python3 "$ROOT/webui/server.py" "${ARGS[@]}"
