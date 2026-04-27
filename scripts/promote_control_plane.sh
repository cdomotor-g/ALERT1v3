#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROLE_FILE="$ROOT/config/deployment_role.json"
ARCHIVE_POLICY="$ROOT/config/archive_policy.json"
ARCHIVE_ENV="$ROOT/config/archive_env"
PULL_FIRST=0
BOOTSTRAP_ONLY=0
FORCE=0
LEASE_SECONDS=300

usage(){
  cat <<EOF
Usage: $0 [--pull-first] [--bootstrap-only] [--force] [--lease-seconds N]

Promotes this host as active control plane and syncs control-plane state via S3-compatible storage.
Reads:
  - config/deployment_role.json (control.state_prefix)
  - config/archive_policy.json   (endpoint/region/bucket)
  - config/archive_env           (AWS credentials)
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pull-first) PULL_FIRST=1; shift ;;
    --bootstrap-only) BOOTSTRAP_ONLY=1; shift ;;
    --force) FORCE=1; shift ;;
    --lease-seconds) LEASE_SECONDS="${2:-300}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1"; usage; exit 2 ;;
  esac
done

[[ -f "$ROLE_FILE" ]] || { echo "missing $ROLE_FILE"; exit 1; }
[[ -f "$ARCHIVE_POLICY" ]] || { echo "missing $ARCHIVE_POLICY"; exit 1; }
[[ -f "$ARCHIVE_ENV" ]] || { echo "missing $ARCHIVE_ENV (copy from config/archive_env.example)"; exit 1; }

set -a
source "$ARCHIVE_ENV"
set +a

python3 - "$ROOT" "$ROLE_FILE" "$ARCHIVE_POLICY" "$PULL_FIRST" "$BOOTSTRAP_ONLY" "$FORCE" "$LEASE_SECONDS" <<'PY'
import json, os, socket, sys, datetime
from pathlib import Path

root = Path(sys.argv[1])
role_file = Path(sys.argv[2])
policy_file = Path(sys.argv[3])
pull_first = bool(int(sys.argv[4]))
bootstrap_only = bool(int(sys.argv[5]))
force = bool(int(sys.argv[6]))
lease_seconds = int(sys.argv[7])

import boto3

role = json.loads(role_file.read_text(encoding='utf-8'))
policy = json.loads(policy_file.read_text(encoding='utf-8'))

r = str(role.get('role','edge')).lower().strip()
if r not in ('control','hybrid','all'):
    raise SystemExit(f"Refusing promote: deployment role is '{r}', expected control/hybrid")

ctrl = role.get('control') or {}
prefix = str(ctrl.get('state_prefix','fwlab/control-plane')).strip().strip('/')
if not prefix:
    raise SystemExit('control.state_prefix is empty')

bucket = str(policy.get('bucket','')).strip()
if not bucket:
    raise SystemExit('archive_policy bucket is empty')

session = boto3.session.Session(
    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
)
s3 = session.client('s3', endpoint_url=policy.get('endpoint') or None, region_name=policy.get('region') or None)

files = [
    root / 'config' / 'meta_catalog.json',
    root / 'config' / 'receivers_registry.json',
    root / 'config' / 'receiver_identity.json',
    root / 'config' / 'deployment_role.json',
    root / 'rf_log' / 'audit' / 'meta_catalog_history.jsonl',
    root / 'rf_log' / 'audit' / 'admin_actions.jsonl',
]

host = socket.gethostname()
ts = datetime.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
run_key = f"{prefix}/snapshots/{ts}_{host}"
local_state = root / 'rf_log' / 'control_plane_bootstrap'
local_state.mkdir(parents=True, exist_ok=True)


def download_latest():
    latest_key = f"{prefix}/latest.json"
    try:
        obj = s3.get_object(Bucket=bucket, Key=latest_key)
    except Exception:
        print('No latest control-plane state found in bucket.')
        return
    latest = json.loads(obj['Body'].read().decode('utf-8', errors='replace'))
    entries = latest.get('files') or []
    print(f"Found latest snapshot: {latest.get('snapshot','?')} with {len(entries)} files")
    for e in entries:
        k = e.get('key')
        rel = e.get('path')
        if not k or not rel:
            continue
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        body = s3.get_object(Bucket=bucket, Key=k)['Body'].read()
        dst.write_bytes(body)
        print(f"restored: {rel}")

if pull_first or bootstrap_only:
    download_latest()

if bootstrap_only:
    print('Bootstrap-only mode complete.')
    raise SystemExit(0)

lock_key = f"{prefix}/promotion_lock.json"
now = datetime.datetime.utcnow()
lock_doc = {
    'schema': 'fwlab.control_plane.lock.v1',
    'host': host,
    'acquired_ts': now.isoformat() + 'Z',
    'lease_seconds': lease_seconds,
}
if not force:
    try:
        cur = s3.get_object(Bucket=bucket, Key=lock_key)
        cur_doc = json.loads(cur['Body'].read().decode('utf-8', errors='replace'))
        ts = str(cur_doc.get('acquired_ts', ''))
        lease = int(cur_doc.get('lease_seconds', lease_seconds) or lease_seconds)
        lock_host = str(cur_doc.get('host', 'unknown'))
        if ts:
            try:
                t0 = datetime.datetime.fromisoformat(ts.replace('Z', '+00:00')).replace(tzinfo=None)
                age = (now - t0).total_seconds()
                if age < lease:
                    raise SystemExit(f"Refusing promote: active promotion lock held by {lock_host} (age={int(age)}s lease={lease}s). Use --force if intentional.")
            except Exception:
                pass
    except Exception:
        pass
s3.put_object(Bucket=bucket, Key=lock_key, Body=(json.dumps(lock_doc, indent=2)+'\n').encode('utf-8'), ContentType='application/json')

entries = []
for p in files:
    if not p.exists():
        continue
    rel = str(p.relative_to(root))
    key = f"{run_key}/{rel}"
    s3.upload_file(str(p), bucket, key)
    entries.append({'path': rel, 'key': key, 'bytes': p.stat().st_size})
    print(f"uploaded: {rel}")

latest = {
    'schema': 'fwlab.control_state.latest.v1',
    'snapshot': f"{ts}_{host}",
    'ts': datetime.datetime.utcnow().isoformat() + 'Z',
    'host': host,
    'role': r,
    'files': entries,
}
active = {
    'schema': 'fwlab.control_plane.active.v1',
    'active_host': host,
    'activated_ts': datetime.datetime.utcnow().isoformat() + 'Z',
    'snapshot': latest['snapshot'],
}

s3.put_object(Bucket=bucket, Key=f"{prefix}/latest.json", Body=(json.dumps(latest, indent=2)+'\n').encode('utf-8'), ContentType='application/json')
s3.put_object(Bucket=bucket, Key=f"{prefix}/active_control_plane.json", Body=(json.dumps(active, indent=2)+'\n').encode('utf-8'), ContentType='application/json')
try:
    s3.delete_object(Bucket=bucket, Key=lock_key)
except Exception:
    pass
print(f"Promoted active control plane: host={host} snapshot={latest['snapshot']}")
PY
