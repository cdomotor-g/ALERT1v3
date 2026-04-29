#!/usr/bin/env bash
set -euo pipefail

HOSTS=("cloud.floodwarning.net" "backup1.floodwarning.net" "fwlab.floodwarning.net")

echo "== DNS + origin reachability =="
for h in "${HOSTS[@]}"; do
  echo "-- $h"
  getent ahostsv4 "$h" | head -n1 || echo "dns unresolved"
  echo -n "  http /api/control/policy: "
  curl -sS -o /dev/null -w "%{http_code}\n" "http://$h/api/control/policy" --max-time 8 || true
  echo -n "  https /api/control/policy: "
  curl -k -sS -o /dev/null -w "%{http_code}\n" "https://$h/api/control/policy" --max-time 8 || true
 done

echo "== Local services =="
systemctl is-active fwlab-webui.service || true
systemctl is-active fwlab-host-monitor.service || true

echo "== Control endpoints =="
curl -sS http://127.0.0.1:8088/api/control/policy | head -c 200; echo
curl -sS http://127.0.0.1:8088/api/control/state_summary | head -c 300; echo
