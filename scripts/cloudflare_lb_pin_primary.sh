#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ENV_FILE:-$ROOT/config/cloudflare_env}"
TARGET="${1:-}"
HOSTNAME="${2:-fwlab.floodwarning.net}"

usage(){ echo "Usage: $0 <righty|pi> [hostname]"; }
[[ -n "$TARGET" ]] || { usage; exit 2; }
[[ -f "$ENV_FILE" ]] || { echo "missing $ENV_FILE"; exit 1; }
set -a; source "$ENV_FILE"; set +a

python3 - "$TARGET" "$HOSTNAME" <<'PY'
import json, os, sys, urllib.request

target=sys.argv[1].strip().lower()
hostname=sys.argv[2]
if target not in ('righty','pi'):
    raise SystemExit('target must be righty or pi')

base='https://api.cloudflare.com/client/v4'
headers={'Authorization': f"Bearer {os.environ['CF_API_TOKEN']}", 'Content-Type':'application/json'}
zone=os.environ['CF_ZONE_ID']
account=os.environ['CF_ACCOUNT_ID']

def call(method,path,data=None):
  b=None if data is None else json.dumps(data).encode('utf-8')
  r=urllib.request.Request(base+path, data=b, headers=headers, method=method)
  with urllib.request.urlopen(r, timeout=30) as resp:
    out=json.loads(resp.read().decode('utf-8','replace'))
  if not out.get('success'):
    raise SystemExit(f"{method} {path} failed: {out.get('errors')}")
  return out.get('result')

lbs=call('GET',f'/zones/{zone}/load_balancers') or []
lb=next((x for x in lbs if x.get('name')==hostname), None)
if not lb:
    raise SystemExit('load balancer hostname not found')

def pool_name(pid):
    p=call('GET',f'/accounts/{account}/load_balancers/pools/{pid}')
    return p.get('name','')

all_pool_ids=[]
for x in (lb.get('default_pools') or []): all_pool_ids.append(x)
if lb.get('fallback_pool'): all_pool_ids.append(lb['fallback_pool'])

righty_pool=next((pid for pid in all_pool_ids if 'righty' in pool_name(pid).lower()), None)
pi_pool=next((pid for pid in all_pool_ids if ('-pi' in pool_name(pid).lower() or pool_name(pid).lower().endswith('pi'))), None)
if not righty_pool or not pi_pool:
    raise SystemExit('could not resolve righty/pi pools by name')

default_pool = righty_pool if target=='righty' else pi_pool
fallback_pool = pi_pool if target=='righty' else righty_pool
payload={
  'name': lb['name'],
  'ttl': lb.get('ttl',30),
  'proxied': lb.get('proxied',True),
  'enabled': lb.get('enabled',True),
  'default_pools': [default_pool],
  'fallback_pool': fallback_pool,
  'steering_policy': lb.get('steering_policy','off'),
  'session_affinity': lb.get('session_affinity','none'),
}
updated=call('PUT',f"/zones/{zone}/load_balancers/{lb['id']}",payload)
print(json.dumps({'ok':True,'hostname':hostname,'pinned_primary':target,'lb_id':updated['id']}, indent=2))
PY
