#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_BASE="${LOG_BASE:-$ROOT/rf_log}"
HOST_METRICS_JSONL="${HOST_METRICS_JSONL:-$LOG_BASE/host_metrics.jsonl}"
MON_INTERVAL="${MON_INTERVAL:-5}"
MQTT_HOST="${MQTT_HOST:-}"
MQTT_PORT="${MQTT_PORT:-1883}"
MQTT_USER="${MQTT_USER:-}"
MQTT_PASS="${MQTT_PASS:-}"
MQTT_PREFIX="${MQTT_PREFIX:-alert}"

mkdir -p "$LOG_BASE"

ARGS=(--interval "$MON_INTERVAL" --output-jsonl "$HOST_METRICS_JSONL")
if [[ -n "$MQTT_HOST" ]]; then
  ARGS+=(--mqtt-host "$MQTT_HOST" --mqtt-port "$MQTT_PORT" --mqtt-topic-prefix "$MQTT_PREFIX")
  if [[ -n "$MQTT_USER" ]]; then
    ARGS+=(--mqtt-username "$MQTT_USER" --mqtt-password "$MQTT_PASS")
  fi
fi

exec python3 "$ROOT/tools/host_monitor.py" "${ARGS[@]}"
