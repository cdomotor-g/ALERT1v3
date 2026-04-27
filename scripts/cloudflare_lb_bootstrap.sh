#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/config/cloudflare_env}"
HOSTNAME="${HOSTNAME:-fwlab.floodwarning.net}"

usage(){
  cat <<EOF
Usage: $0 --righty <origin-host-or-ip> --pi <origin-host-or-ip> [--hostname fwlab.floodwarning.net]

Creates/updates Cloudflare LB monitor + pools + hostname LB.
Requires config/cloudflare_env with:
  CF_API_TOKEN, CF_ACCOUNT_ID, CF_ZONE_ID
EOF
}

RIGHTY=""
PI=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --righty) RIGHTY="${2:-}"; shift 2 ;;
    --pi) PI="${2:-}"; shift 2 ;;
    --hostname) HOSTNAME="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1"; usage; exit 2 ;;
  esac
done

[[ -n "$RIGHTY" && -n "$PI" ]] || { usage; exit 2; }
[[ -f "$ENV_FILE" ]] || { echo "missing $ENV_FILE"; exit 1; }

set -a
source "$ENV_FILE"
set +a

python3 - "$RIGHTY" "$PI" "$HOSTNAME" <<'PY'
import json, os, sys, urllib.request

righty, pi, hostname = sys.argv[1], sys.argv[2], sys.argv[3]

token = os.environ.get('CF_API_TOKEN','').strip()
account = os.environ.get('CF_ACCOUNT_ID','').strip()
zone = os.environ.get('CF_ZONE_ID','').strip()
if not all([token, account, zone]):
    raise SystemExit('CF_API_TOKEN / CF_ACCOUNT_ID / CF_ZONE_ID required')

base = 'https://api.cloudflare.com/client/v4'
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}


def req(method, path, data=None):
    body = None if data is None else json.dumps(data).encode('utf-8')
    r = urllib.request.Request(base + path, data=body, headers=headers, method=method)
    with urllib.request.urlopen(r, timeout=30) as resp:
        out = json.loads(resp.read().decode('utf-8', errors='replace'))
    if not out.get('success'):
        raise SystemExit(f"Cloudflare API failed {method} {path}: {out.get('errors')}")
    return out.get('result')


def list_all(path):
    return req('GET', path)


def upsert_monitor(name, path='/api/control/policy'):
    mons = list_all(f'/accounts/{account}/load_balancers/monitors') or []
    m = next((x for x in mons if x.get('description') == name or x.get('type') == 'https' and x.get('path') == path), None)
    payload = {
        'type': 'https',
        'description': name,
        'method': 'GET',
        'path': path,
        'port': 443,
        'timeout': 5,
        'retries': 2,
        'interval': 60,
        'follow_redirects': True,
        'expected_codes': '200',
    }
    if m:
        return req('PUT', f"/accounts/{account}/load_balancers/monitors/{m['id']}", payload)
    return req('POST', f'/accounts/{account}/load_balancers/monitors', payload)


def upsert_pool(name, origin_host, monitor_id):
    pools = list_all(f'/accounts/{account}/load_balancers/pools') or []
    p = next((x for x in pools if x.get('name') == name), None)
    payload = {
        'name': name,
        'enabled': True,
        'monitor': monitor_id,
        'check_regions': ['WNAM','ENAM','WEU','EEU','SEAS','NEAS','OC'],
        'origins': [
            {'name': name + '-origin', 'address': origin_host, 'enabled': True, 'weight': 1}
        ]
    }
    if p:
        return req('PUT', f"/accounts/{account}/load_balancers/pools/{p['id']}", payload)
    return req('POST', f'/accounts/{account}/load_balancers/pools', payload)


def upsert_lb(hostname, default_pool_id, fallback_pool_id):
    lbs = list_all(f'/zones/{zone}/load_balancers') or []
    lb = next((x for x in lbs if x.get('name') == hostname), None)
    payload = {
        'name': hostname,
        'ttl': 30,
        'proxied': True,
        'enabled': True,
        'default_pools': [default_pool_id],
        'fallback_pool': fallback_pool_id,
        'steering_policy': 'off',
        'session_affinity': 'none',
    }
    if lb:
        return req('PUT', f"/zones/{zone}/load_balancers/{lb['id']}", payload)
    return req('POST', f'/zones/{zone}/load_balancers', payload)

monitor = upsert_monitor('fwlab-cp-monitor', '/api/control/policy')
righty_pool = upsert_pool('fwlab-cp-righty', righty, monitor['id'])
pi_pool = upsert_pool('fwlab-cp-pi', pi, monitor['id'])
lb = upsert_lb(hostname, righty_pool['id'], pi_pool['id'])

print(json.dumps({
    'ok': True,
    'monitor_id': monitor['id'],
    'righty_pool_id': righty_pool['id'],
    'pi_pool_id': pi_pool['id'],
    'lb_id': lb['id'],
    'hostname': hostname,
    'default': 'righty',
    'fallback': 'pi',
}, indent=2))
PY
