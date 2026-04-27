#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROLE_FILE="$ROOT/config/deployment_role.json"
POLICY_FILE="$ROOT/config/archive_policy.json"
ENV_FILE="$ROOT/config/archive_env"

usage(){
  cat <<EOF
Usage: $0

Reads control-plane status artifacts from S3-compatible storage:
  - <state_prefix>/active_control_plane.json
  - <state_prefix>/latest.json
Requires:
  - config/deployment_role.json
  - config/archive_policy.json
  - config/archive_env
EOF
}

[[ "${1:-}" =~ ^(-h|--help)$ ]] && { usage; exit 0; }

[[ -f "$ROLE_FILE" ]] || { echo "missing $ROLE_FILE"; exit 1; }
[[ -f "$POLICY_FILE" ]] || { echo "missing $POLICY_FILE"; exit 1; }
[[ -f "$ENV_FILE" ]] || { echo "missing $ENV_FILE"; exit 1; }

set -a
source "$ENV_FILE"
set +a

python3 - "$ROLE_FILE" "$POLICY_FILE" <<'PY'
import json, os, sys
from pathlib import Path

import boto3

role_file=Path(sys.argv[1])
policy_file=Path(sys.argv[2])

role=json.loads(role_file.read_text(encoding='utf-8'))
policy=json.loads(policy_file.read_text(encoding='utf-8'))
prefix=str(((role.get('control') or {}).get('state_prefix') or 'fwlab/control-plane')).strip('/ ')
bucket=str(policy.get('bucket','')).strip()
if not bucket:
    raise SystemExit('archive_policy bucket missing')

session=boto3.session.Session(
    aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY'),
)
s3=session.client('s3', endpoint_url=policy.get('endpoint') or None, region_name=policy.get('region') or None)

def load_json(key):
    try:
        obj=s3.get_object(Bucket=bucket, Key=key)
        return json.loads(obj['Body'].read().decode('utf-8', errors='replace'))
    except Exception as e:
        return {'_error': str(e), '_key': key}

active=load_json(f"{prefix}/active_control_plane.json")
latest=load_json(f"{prefix}/latest.json")
endpoint=load_json(f"{prefix}/active_endpoint.json")

print('== control plane status ==')
print(f"bucket: {bucket}")
print(f"prefix: {prefix}")
print('\n[active_control_plane.json]')
print(json.dumps(active, indent=2))
print('\n[latest.json]')
print(json.dumps(latest, indent=2))
print('\n[active_endpoint.json]')
print(json.dumps(endpoint, indent=2))
PY
