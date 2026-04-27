#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BASE_URL="${BASE_URL:-http://127.0.0.1:8088}"
RXS_ID="${RXS_ID:-0000}"

echo "== Control-plane drill start =="

echo "[1/6] Role -> control (apply + verify)"
"$ROOT/scripts/set_role.sh" control --apply --verify

echo "[2/6] Bootstrap latest CP state (no promote)"
"$ROOT/scripts/promote_control_plane.sh" --bootstrap-only || true

echo "[3/6] Promote this host as active CP"
"$ROOT/scripts/promote_control_plane.sh" --pull-first

echo "[4/6] Inspect S3 CP status + sync local active endpoint pointer"
"$ROOT/scripts/control_plane_status.sh"
"$ROOT/scripts/sync_active_control_endpoint.sh" || true

echo "[5/6] Ingest synthetic heartbeat/events"
curl -sS -X POST "$BASE_URL/api/control/ingest" \
  -H 'Content-Type: application/json' \
  -d "{\"rxs_id\":\"$RXS_ID\",\"heartbeat\":{\"state\":\"online\",\"note\":\"drill\"},\"stats\":{\"decoder\":\"ok\"},\"events\":[{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"decode\":{\"sensor_id\":\"drill.$RXS_ID\"}}]}" | sed -n '1,120p'

echo

echo "[6/6] Verify ingest + receiver snapshots"
curl -sS "$BASE_URL/api/control/receivers" | sed -n '1,160p'
curl -sS "$BASE_URL/api/control/receiver_latest?rxs_id=$RXS_ID" | sed -n '1,160p'

echo "== Control-plane drill complete =="
