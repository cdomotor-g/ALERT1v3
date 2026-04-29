#!/usr/bin/env bash
set -euo pipefail

PROFILE="all"
TARGET_USER="${SUDO_USER:-$USER}"
BASE_URL="http://127.0.0.1:8088"

usage(){ cat <<EOF
Usage: $0 [--profile all|webui|receiver|control] [--user USER] [--base-url URL]
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="$2"; shift 2 ;;
    --user) TARGET_USER="$2"; shift 2 ;;
    --base-url) BASE_URL="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1"; exit 2 ;;
  esac
done

units=(fwlab-webui.service)
case "$PROFILE" in
  all) units+=(fwlab-receiver.service fwlab-host-monitor.service fwlab-rx-agg.service) ;;
  receiver) units+=(fwlab-receiver.service fwlab-host-monitor.service fwlab-rx-agg.service) ;;
  control) units+=(fwlab-host-monitor.service) ;;
  webui) ;;
  *) echo "invalid profile: $PROFILE"; exit 2 ;;
esac

echo "== service states =="
for u in "${units[@]}"; do
  if systemctl list-unit-files "$u" >/dev/null 2>&1; then
    st="$(systemctl is-active "$u" 2>/dev/null || true)"
    echo "$u: $st"
  else
    echo "$u: not-installed"
  fi
done

echo "== web checks =="
curl -sS -o /dev/null -w "GET / => %{http_code}\n" "$BASE_URL/" || true
curl -sS -o /dev/null -w "GET /help => %{http_code}\n" "$BASE_URL/help" || true
curl -sS -o /dev/null -w "GET /bitflipper => %{http_code}\n" "$BASE_URL/bitflipper" || true
curl -sS -o /dev/null -w "GET /api/receiver_info => %{http_code}\n" "$BASE_URL/api/receiver_info" || true

echo "== quick diagnostics =="
systemctl --no-pager --full status fwlab-webui.service | sed -n '1,30p' || true
