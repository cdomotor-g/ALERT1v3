#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROLE_FILE="$ROOT/config/deployment_role.json"
POLICY_FILE="$ROOT/config/archive_policy.json"
ENV_FILE="$ROOT/config/archive_env"
ENDPOINTS_FILE="$ROOT/config/control_plane_endpoints.json"

[[ -f "$ROLE_FILE" ]] || { echo "missing $ROLE_FILE"; exit 1; }
[[ -f "$POLICY_FILE" ]] || { echo "missing $POLICY_FILE"; exit 1; }
[[ -f "$ENV_FILE" ]] || { echo "missing $ENV_FILE"; exit 1; }
[[ -f "$ENDPOINTS_FILE" ]] || { echo "missing $ENDPOINTS_FILE"; exit 1; }

set -a
source "$ENV_FILE"
set +a

python3 - "$ROLE_FILE" "$POLICY_FILE" "$ENDPOINTS_FILE" <<'PY'
import json, os, sys
from pathlib import Path
import boto3

role=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
policy=json.loads(Path(sys.argv[2]).read_text(encoding='utf-8'))
ep_path=Path(sys.argv[3])
ep=json.loads(ep_path.read_text(encoding='utf-8'))

prefix=str(((role.get('control') or {}).get('state_prefix') or 'fwlab/control-plane')).strip('/ ')
bucket=str(policy.get('bucket','')).strip()
if not bucket:
    raise SystemExit('archive_policy bucket missing')

session=boto3.session.Session(
  aws_access_key_id=os.environ.get('AWS_ACCESS_KEY_ID'),
  aws_secret_access_key=os.environ.get('AWS_SECRET_ACCESS_KEY')
)
s3=session.client('s3', endpoint_url=policy.get('endpoint') or None, region_name=policy.get('region') or None)
key=f"{prefix}/active_endpoint.json"
obj=s3.get_object(Bucket=bucket, Key=key)
d=json.loads(obj['Body'].read().decode('utf-8', errors='replace'))
url=str(d.get('activeBaseUrl','')).strip().rstrip('/')
if not url:
    raise SystemExit('active_endpoint.json missing activeBaseUrl')
ep['activeBaseUrl']=url
ep_path.write_text(json.dumps(ep, indent=2)+'\n', encoding='utf-8')
print('synced activeBaseUrl ->', url)
PY
