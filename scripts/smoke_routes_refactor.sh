#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8088}"

echo "[smoke] BASE_URL=${BASE_URL}"

check_get() {
  local path="$1"
  echo "[GET] ${path}"
  curl -fsS "${BASE_URL}${path}" >/dev/null
}

check_post_json() {
  local path="$1"
  local body="$2"
  echo "[POST] ${path}"
  curl -fsS -X POST "${BASE_URL}${path}" -H 'Content-Type: application/json' -d "${body}" >/dev/null
}

# core modularized GETs
check_get "/api/control/policy"
check_get "/api/receivers_registry"
check_get "/api/stations/catalog?limit=1"
check_get "/api/file_drop/list?limit=1"
check_get "/api/sensor_map/status"
check_get "/api/path/defaults"
check_get "/api/meta/catalog"
check_get "/api/deployment_role"
check_get "/api/rx_agg" || true
check_get "/api/events?limit=1"
check_get "/api/sensors?source=auto"
check_get "/api/views"
check_get "/api/error_stats?limit=10&mode=occurrence"
check_get "/api/anomaly_stats?limit=10"
check_get "/api/forensics_bundle?limit=5"
check_get "/api/pair_pattern_stats?limit=10"
check_get "/api/flowgraph_doc"
check_get "/api/storage_status"
check_get "/api/receiver_status"
check_get "/api/host_metrics"
check_get "/api/trends?sensor_id=&window=24h&source=auto&metric=raw&limit=100"

# safe POST probes (non-destructive where possible)
check_post_json "/api/path/defaults" '{}'
check_post_json "/api/views" '{"name":"smoke","sensor_id":""}'
check_post_json "/api/file_drop/upload" '{"filename":"smoke.txt","content":"ok"}'

# NOTE: admin endpoints may require auth and are intentionally not hard-failed here
for admin_path in \
  "/api/admin/storage_policy" \
  "/api/admin/rf_control" \
  "/api/admin/audit_recent?limit=1" \
  "/api/admin/meta/history?limit=1"
do
  echo "[GET optional-admin] ${admin_path}"
  curl -sS "${BASE_URL}${admin_path}" >/dev/null || true
done

echo "[smoke] completed"
