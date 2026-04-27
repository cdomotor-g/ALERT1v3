#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/config/cloudflare_env}"
HOSTNAME="${1:-fwlab.floodwarning.net}"

[[ -f "$ENV_FILE" ]] || { echo "missing $ENV_FILE"; exit 1; }
set -a; source "$ENV_FILE"; set +a

python3 - "$HOSTNAME" <<'PY'
import json, os, sys, urllib.request
hostname=sys.argv[1]
base='https://api.cloudflare.com/client/v4'
headers={'Authorization': f"Bearer {os.environ['CF_API_TOKEN']}", 'Content-Type':'application/json'}
zone=os.environ['CF_ZONE_ID']
account=os.environ['CF_ACCOUNT_ID']

def get(path):
  r=urllib.request.Request(base+path, headers=headers)
  with urllib.request.urlopen(r, timeout=30) as resp:
    out=json.loads(resp.read().decode('utf-8','replace'))
  if not out.get('success'):
    raise SystemExit(out)
  return out.get('result')

lbs=get(f'/zones/{zone}/load_balancers') or []
lb=next((x for x in lbs if x.get('name')==hostname), None)
if not lb:
  print(json.dumps({'ok':False,'error':'lb_not_found','hostname':hostname}, indent=2)); raise SystemExit(0)

pool_ids=[*(lb.get('default_pools') or []), lb.get('fallback_pool')]
pools=[]
for pid in [p for p in pool_ids if p]:
  pools.append(get(f'/accounts/{account}/load_balancers/pools/{pid}'))

print(json.dumps({'ok':True,'lb':lb,'pools':pools}, indent=2))
PY
