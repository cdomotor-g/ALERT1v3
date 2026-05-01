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
UPDATE_MODE=0
SELF_UPDATE=0
ORIGIN_HOSTNAME=""
CF_TUNNEL_ID=""
CF_TUNNEL_SECRET=""
CF_ACCOUNT_TAG=""
CF_ROUTE_DNS=0
PRESET=""

usage() {
  cat <<EOF
FW-LAB installer

Usage: $0 [options]
  --profile <auto|all|webui|receiver|control>
  --user <linux_user>         Install/run services as this user (default: ${TARGET_USER})
  --yes                       Non-interactive (assume yes)
  --dry-run                   Print actions without changing system
  --skip-deps                 Skip package installation
  --update                    Run as install/update pass (safe re-run)
  --self-update               Git fetch + reset to origin/main before install
  --preset <name>             Load tunnel/origin settings from config/tunnel_role.json preset
  --origin-hostname <fqdn>    Configure nginx+certbot TLS reverse proxy to :8088
  --cf-tunnel-id <id>         Cloudflare Tunnel UUID (managed mode)
  --cf-tunnel-secret <b64>    Cloudflare Tunnel secret (base64)
  --cf-account-tag <id>       Cloudflare account tag for tunnel credentials
  --cf-route-dns              Run 'cloudflared tunnel route dns <id> <origin-hostname>'
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
    --update) UPDATE_MODE=1; shift ;;
    --self-update) SELF_UPDATE=1; shift ;;
    --preset) PRESET="${2:-}"; shift 2 ;;
    --origin-hostname) ORIGIN_HOSTNAME="${2:-}"; shift 2 ;;
    --cf-tunnel-id) CF_TUNNEL_ID="${2:-}"; shift 2 ;;
    --cf-tunnel-secret) CF_TUNNEL_SECRET="${2:-}"; shift 2 ;;
    --cf-account-tag) CF_ACCOUNT_TAG="${2:-}"; shift 2 ;;
    --cf-route-dns) CF_ROUTE_DNS=1; shift ;;
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

if [[ "$SELF_UPDATE" -eq 1 && "$DRY_RUN" -eq 0 ]]; then
  if [[ -d "$ROOT/.git" ]]; then
    echo "Self-updating repo at $ROOT"
    git -C "$ROOT" fetch origin || true
    git -C "$ROOT" checkout main || true
    git -C "$ROOT" reset --hard origin/main || true
  else
    echo "WARN: --self-update requested but $ROOT is not a git repo"
  fi
fi

if [[ -n "$PRESET" ]]; then
  PRESET_FILE="$ROOT/config/tunnel_role.json"
  if [[ ! -f "$PRESET_FILE" ]]; then
    echo "ERROR: preset requested but missing $PRESET_FILE (copy from config/tunnel_role.example.json)" >&2
    exit 1
  fi
  eval "$(python3 - <<'PY'
import json
from pathlib import Path
p=Path('config/tunnel_role.json')
d=json.loads(p.read_text(encoding='utf-8'))
pr=(d.get('presets') or {}).get('''$PRESET''') or {}
for k,key in [('ORIGIN_HOSTNAME','originHostname'),('CF_TUNNEL_ID','tunnelId'),('CF_ACCOUNT_TAG','accountTag'),('CF_TUNNEL_SECRET','tunnelSecret')]:
    v=str(pr.get(key,'')).replace('"','\\"')
    print(f'{k}="{v}"')
print('CF_ROUTE_DNS='+('1' if bool(pr.get('routeDns',False)) else '0'))
PY
)"
  echo "Loaded preset '$PRESET' from config/tunnel_role.json"
fi

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
    jq nginx certbot python3-certbot-nginx
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
    fwlab-auto-update.service
    fwlab-auto-update.timer
  )
  # control-sync units are deprecated in S3-driven control-plane model
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

# Retire legacy control-sync in favor of S3 control-plane state model.
run "sudo systemctl disable --now fwlab-control-sync.timer fwlab-control-sync.service 2>/dev/null || true"

enable_for_profile() {
  local en=(fwlab-webui.service fwlab-host-monitor.service)
  local timers=(fwlab-log-retention.timer fwlab-archive-uploader.timer fwlab-auto-update.timer)
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
      timers=(fwlab-log-retention.timer fwlab-archive-uploader.timer)
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

configure_cloudflared_tunnel() {
  local host="$1"
  local tid="$2"
  local tsec="$3"
  local acct="$4"
  [[ -n "$host" && -n "$tid" && -n "$tsec" && -n "$acct" ]] || return 0

  echo "Configuring cloudflared managed tunnel for $host"
  run "sudo mkdir -p /etc/cloudflared"
  run "sudo apt-get update"
  run "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y cloudflared"

  run "cat > /tmp/fwlab_tunnel.json <<EOF
{
  \"AccountTag\": \"$acct\",
  \"TunnelID\": \"$tid\",
  \"TunnelSecret\": \"$tsec\"
}
EOF"
  run "sudo mv /tmp/fwlab_tunnel.json /etc/cloudflared/$tid.json"
  run "sudo chown root:root /etc/cloudflared/$tid.json"
  run "sudo chmod 600 /etc/cloudflared/$tid.json"

  # Render YAML via Python to avoid shell/heredoc formatting edge cases.
  run "python3 - <<'PY'
from pathlib import Path
tid = '''$tid'''.strip()
host = '''$host'''.strip()
yml = f'''tunnel: {tid}\ncredentials-file: /etc/cloudflared/{tid}.json\ningress:\n  - hostname: {host}\n    service: http://127.0.0.1:8088\n  - service: http_status:404\n'''
Path('/tmp/fwlab_cloudflared.yml').write_text(yml, encoding='utf-8')
PY"
  run "sudo mv /tmp/fwlab_cloudflared.yml /etc/cloudflared/config.yml"

  if [[ "$CF_ROUTE_DNS" -eq 1 ]]; then
    run "sudo cloudflared tunnel route dns $tid $host || true"
  fi

  if ! sudo cloudflared tunnel --config /etc/cloudflared/config.yml ingress validate; then
    echo "cloudflared ingress validate failed; dumping /etc/cloudflared/config.yml with line numbers:" >&2
    sudo nl -ba /etc/cloudflared/config.yml >&2 || true
    return 1
  fi
  run "sudo systemctl enable --now cloudflared"
  run "sudo systemctl restart cloudflared"

  if [[ "$DRY_RUN" -eq 0 ]]; then
    sleep 4
    systemctl is-active cloudflared || true
    sudo journalctl -u cloudflared -n 30 --no-pager || true
    curl -sS -o /dev/null -w "edge root (%{http_code})\n" "https://$host/" --max-time 15 || true
    curl -sS -o /dev/null -w "edge policy (%{http_code})\n" "https://$host/api/control/policy" --max-time 15 || true
  fi
}

configure_origin_tls() {
  local host="$1"
  [[ -n "$host" ]] || return 0
  echo "Configuring HTTPS reverse proxy for $host -> 127.0.0.1:8088"
  run "sudo mkdir -p /etc/nginx/sites-available /etc/nginx/sites-enabled"
  run "cat > /tmp/fwlab_origin_nginx.conf <<'NG'
server {
  listen 80;
  server_name ${host};
  location /.well-known/acme-challenge/ { root /var/www/html; }
  location / { proxy_pass http://127.0.0.1:8088; }
}
NG"
  run "sed -i 's|\${host}|$host|g' /tmp/fwlab_origin_nginx.conf"
  run "sudo mv /tmp/fwlab_origin_nginx.conf /etc/nginx/sites-available/fwlab-origin.conf"
  run "sudo ln -sf /etc/nginx/sites-available/fwlab-origin.conf /etc/nginx/sites-enabled/fwlab-origin.conf"
  run "sudo nginx -t"
  run "sudo systemctl enable --now nginx"
  run "sudo systemctl reload nginx"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    sudo certbot --nginx -d "$host" --non-interactive --agree-tos -m "admin@${host#*.}" --redirect || true
    curl -k -sS -o /dev/null -w "origin https check (%{http_code})\n" "https://$host/api/control/policy" --max-time 10 || true
  fi
}

if [[ -n "$ORIGIN_HOSTNAME" ]]; then
  if [[ -n "$CF_TUNNEL_ID" && -n "$CF_TUNNEL_SECRET" && -n "$CF_ACCOUNT_TAG" ]]; then
    configure_cloudflared_tunnel "$ORIGIN_HOSTNAME" "$CF_TUNNEL_ID" "$CF_TUNNEL_SECRET" "$CF_ACCOUNT_TAG"
  else
    configure_origin_tls "$ORIGIN_HOSTNAME"
  fi
fi

if [[ "$DRY_RUN" -eq 0 ]]; then
  "$ROOT/scripts/verify_fwlab.sh" --profile "$PROFILE" --user "$TARGET_USER" || true
fi

echo
echo "FW-LAB install complete. Log: $LOG_FILE"
