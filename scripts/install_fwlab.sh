#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$ROOT/rf_log/install"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/install_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1

PROFILE="auto"          # auto|all|webui|receiver|control
TARGET_USER="${SUDO_USER:-$USER}"
ASSUME_YES=0
DRY_RUN=0
SKIP_DEPS=0

usage() {
  cat <<EOF
FW-LAB installer

Usage: $0 [options]
  --profile <auto|all|webui|receiver|control>
  --user <linux_user>         Install/run services as this user (default: ${TARGET_USER})
  --yes                       Non-interactive (assume yes)
  --dry-run                   Print actions without changing system
  --skip-deps                 Skip package installation
  -h, --help
EOF
}

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] $*"
  else
    eval "$@"
  fi
}

need_cmd() { command -v "$1" >/dev/null 2>&1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="${2:-}"; shift 2 ;;
    --user) TARGET_USER="${2:-}"; shift 2 ;;
    --yes) ASSUME_YES=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --skip-deps) SKIP_DEPS=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1"; usage; exit 2 ;;
  esac
done

if [[ "$PROFILE" == "auto" ]]; then
  ROLE_FILE="$ROOT/config/deployment_role.json"
  ROLE=""
  if [[ -f "$ROLE_FILE" ]]; then
    ROLE="$(python3 - <<'PY'
import json
from pathlib import Path
p=Path('config/deployment_role.json')
try:
  d=json.loads(p.read_text(encoding='utf-8'))
  print(str(d.get('role','')).strip().lower())
except Exception:
  print('')
PY
)"
  fi
  case "$ROLE" in
    edge|node) PROFILE="receiver" ;;
    control|control-plane) PROFILE="control" ;;
    hybrid|all) PROFILE="all" ;;
    *) PROFILE="all" ;;
  esac
  echo "Auto profile resolved from deployment role '$ROLE' -> '$PROFILE'"
fi

case "$PROFILE" in all|webui|receiver|control) ;; *) echo "invalid profile: $PROFILE"; exit 2 ;; esac

if ! need_cmd systemctl; then
  echo "ERROR: systemd required (systemctl missing)." >&2
  exit 1
fi

if ! id "$TARGET_USER" >/dev/null 2>&1; then
  echo "ERROR: user '$TARGET_USER' does not exist" >&2
  exit 1
fi

TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
if [[ -z "$TARGET_HOME" || ! -d "$TARGET_HOME" ]]; then
  echo "ERROR: could not resolve home dir for $TARGET_USER" >&2
  exit 1
fi

if [[ "$ASSUME_YES" -ne 1 ]]; then
  echo "About to install FW-LAB profile='$PROFILE' as user='$TARGET_USER' home='$TARGET_HOME'"
  read -r -p "Continue? [y/N] " yn
  [[ "${yn,,}" == "y" ]] || exit 0
fi

install_deps_debian() {
  local pkgs=(
    git curl ca-certificates
    python3 python3-pip python3-venv
    python3-yaml python3-websockets python3-paho-mqtt python3-packaging python3-boto3
    jq
  )
  if [[ "$PROFILE" == "all" || "$PROFILE" == "receiver" ]]; then
    pkgs+=(gnuradio gr-osmosdr rtl-sdr)
  fi
  run "sudo apt-get update"
  run "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y ${pkgs[*]}"
}

if [[ "$SKIP_DEPS" -ne 1 ]]; then
  if [[ -f /etc/debian_version ]]; then
    install_deps_debian
  else
    echo "WARN: non-Debian distro detected; dependency auto-install skipped."
  fi
fi

run "mkdir -p '$ROOT/rf_log' '$ROOT/config' '$TARGET_HOME/rf_log' '$LOG_DIR'"

render_unit() {
  local src="$1" dst="$2"
  run "sudo sed \
    -e 's|User=cdomotor|User=${TARGET_USER}|g' \
    -e 's|Group=cdomotor|Group=${TARGET_USER}|g' \
    -e 's|/home/cdomotor/.openclaw/workspace/projects/ALERT1v3|${ROOT}|g' \
    -e 's|/home/cdomotor|${TARGET_HOME}|g' \
    '${src}' > /tmp/fwlab_unit.tmp"
  run "sudo mv /tmp/fwlab_unit.tmp '${dst}'"
  run "sudo chmod 644 '${dst}'"
}

install_units() {
  local units=(
    fwlab-webui.service
    fwlab-host-monitor.service
    fwlab-receiver.service
    fwlab-log-retention.service
    fwlab-log-retention.timer
    fwlab-archive-uploader.service
    fwlab-archive-uploader.timer
  )
  if [[ "$PROFILE" == "control" ]]; then
    units+=(fwlab-control-sync.service fwlab-control-sync.timer)
  fi
  if [[ "$PROFILE" == "all" || "$PROFILE" == "receiver" ]]; then
    units+=(fwlab-rx-agg.service)
  fi
  for u in "${units[@]}"; do
    [[ -f "$ROOT/deploy/$u" ]] || continue
    render_unit "$ROOT/deploy/$u" "/etc/systemd/system/$u"
  done
}

install_units
run "chmod +x '$ROOT/tools/'*.sh '$ROOT/tools/fwlabctl' || true"
run "sudo systemctl daemon-reload"

enable_for_profile() {
  local en=(fwlab-webui.service fwlab-host-monitor.service)
  local timers=(fwlab-log-retention.timer fwlab-archive-uploader.timer)
  case "$PROFILE" in
    receiver)
      en=(fwlab-receiver.service fwlab-webui.service fwlab-host-monitor.service fwlab-rx-agg.service)
      ;;
    webui)
      en=(fwlab-webui.service)
      timers=()
      ;;
    control)
      en=(fwlab-webui.service fwlab-host-monitor.service)
      timers=(fwlab-log-retention.timer fwlab-archive-uploader.timer fwlab-control-sync.timer)
      # fwlab-control-sync.service is oneshot and should run via timer/on-demand, not --now on install.
      ;;
    all)
      en=(fwlab-receiver.service fwlab-webui.service fwlab-host-monitor.service fwlab-rx-agg.service)
      ;;
  esac
  if [[ ${#en[@]} -gt 0 ]]; then
    run "sudo systemctl enable --now ${en[*]}"
    # ensure latest code is loaded after upgrades/edits
    run "sudo systemctl restart ${en[*]}"
  fi
  if [[ ${#timers[@]} -gt 0 ]]; then
    run "sudo systemctl enable --now ${timers[*]}"
  fi
}

enable_for_profile

if [[ "$DRY_RUN" -eq 0 ]]; then
  "$ROOT/scripts/verify_fwlab.sh" --profile "$PROFILE" --user "$TARGET_USER" || true
fi

echo
echo "FW-LAB install complete. Log: $LOG_FILE"
