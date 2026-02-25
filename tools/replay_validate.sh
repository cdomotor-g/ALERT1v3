#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="${TMPDIR:-/tmp}/alert1v3-replay-$$"
MQTT_PORT="${MQTT_PORT:-18884}"
MQTT_PREFIX="${MQTT_PREFIX:-alert}"

mkdir -p "$TMP"
MOSQ_CONF="$TMP/mosquitto.conf"
cat > "$MOSQ_CONF" <<EOF
listener ${MQTT_PORT} 127.0.0.1
allow_anonymous true
persistence false
log_type error
EOF

cleanup() {
  [[ -n "${MOSQ_PID:-}" ]] && kill "$MOSQ_PID" 2>/dev/null || true
  [[ -n "${SUB_PID:-}" ]] && kill "$SUB_PID" 2>/dev/null || true
  [[ -n "${WEB_PID:-}" ]] && kill "$WEB_PID" 2>/dev/null || true
}
trap cleanup EXIT

MOSQUITTO_BIN="$(command -v mosquitto || true)"
if [[ -z "$MOSQUITTO_BIN" && -x /usr/sbin/mosquitto ]]; then MOSQUITTO_BIN=/usr/sbin/mosquitto; fi
if [[ -z "$MOSQUITTO_BIN" ]]; then
  echo "ERROR: mosquitto binary not found" >&2
  exit 10
fi

"$MOSQUITTO_BIN" -c "$MOSQ_CONF" > "$TMP/mosq.log" 2>&1 &
MOSQ_PID=$!
sleep 0.6

timeout 12s mosquitto_sub -h 127.0.0.1 -p "$MQTT_PORT" -t "$MQTT_PREFIX/rx/#" -C 20 -v > "$TMP/mqtt.log" &
SUB_PID=$!

REPLAY_JSON="$(python3 "$ROOT/tools/replay_pipeline.py" --frames 20 --log-base "$TMP/logs" --mqtt-host 127.0.0.1 --mqtt-port "$MQTT_PORT" --mqtt-prefix "$MQTT_PREFIX")"
echo "$REPLAY_JSON" > "$TMP/replay.json"
JSONL_PATH="$(python3 - <<'PY' "$TMP/replay.json"
import json,sys
print(json.load(open(sys.argv[1]))['jsonl'])
PY
)"

wait "$SUB_PID" || true

python3 "$ROOT/webui/server.py" --jsonl "$JSONL_PATH" --host 127.0.0.1 --port 18088 > "$TMP/web.log" 2>&1 &
WEB_PID=$!
sleep 1
WEB_COUNT="$(curl -s 'http://127.0.0.1:18088/api/events?limit=200' | python3 -c 'import sys,json; print(json.load(sys.stdin).get("count",0))')"

MQTT_LINES="$(wc -l < "$TMP/mqtt.log")"
JSONL_LINES="$(wc -l < "$JSONL_PATH")"

echo "replay_dir=$TMP"
echo "jsonl=$JSONL_PATH"
echo "jsonl_lines=$JSONL_LINES"
echo "mqtt_lines=$MQTT_LINES"
echo "web_count=$WEB_COUNT"

if [[ "$JSONL_LINES" -lt 1 ]]; then
  echo "ERROR: no JSONL events written" >&2
  exit 2
fi
if [[ "$MQTT_LINES" -lt 1 ]]; then
  echo "ERROR: no MQTT events captured" >&2
  exit 3
fi
if [[ "$WEB_COUNT" -lt 1 ]]; then
  echo "ERROR: web API saw no events" >&2
  exit 4
fi

echo "OK: decoder->logger->web/mqtt replay validation passed"
