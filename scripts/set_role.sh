#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROLE_FILE="$ROOT/config/deployment_role.json"
ROLE="${1:-}"
APPLY=0
VERIFY=0

usage(){
  cat <<EOF
Usage: $0 <edge|control|hybrid> [--apply] [--verify]

Options:
  --apply   run installer with --profile auto --yes after updating role
  --verify  run verify script after apply/update
EOF
}

[[ -n "$ROLE" ]] || { usage; exit 2; }
shift || true

while [[ $# -gt 0 ]]; do
  case "$1" in
    --apply) APPLY=1; shift ;;
    --verify) VERIFY=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1"; usage; exit 2 ;;
  esac
done

case "$ROLE" in
  edge|control|hybrid) ;;
  *) echo "Invalid role '$ROLE' (expected edge|control|hybrid)"; exit 2 ;;
esac

mkdir -p "$(dirname "$ROLE_FILE")"

if [[ ! -f "$ROLE_FILE" ]]; then
  cat > "$ROLE_FILE" <<'JSON'
{
  "schema": "fwlab.deployment_role.v1",
  "role": "edge",
  "receiver": {
    "rxs_id": "0000",
    "name": "FW-LAB Receiver",
    "location": "unknown"
  },
  "control": {
    "enabled": false,
    "state_backend": "s3",
    "state_prefix": "fwlab/control-plane"
  }
}
JSON
fi

python3 - "$ROLE_FILE" "$ROLE" <<'PY'
import json, sys
from pathlib import Path
p=Path(sys.argv[1])
role=sys.argv[2]
try:
    d=json.loads(p.read_text(encoding='utf-8'))
except Exception:
    d={}
if not isinstance(d, dict):
    d={}
d.setdefault('schema','fwlab.deployment_role.v1')
d['role']=role
d.setdefault('receiver', {'rxs_id':'0000','name':'FW-LAB Receiver','location':'unknown'})
d.setdefault('control', {'enabled':False,'state_backend':'s3','state_prefix':'fwlab/control-plane'})
d['control']['enabled'] = (role in ('control','hybrid'))
p.write_text(json.dumps(d, indent=2)+'\n', encoding='utf-8')
print(f"role updated: {role}")
PY

if [[ "$APPLY" -eq 1 ]]; then
  "$ROOT/scripts/install_fwlab.sh" --profile auto --yes
fi

if [[ "$VERIFY" -eq 1 ]]; then
  "$ROOT/scripts/verify_fwlab.sh" --profile all
fi

echo "Done. deployment role file: $ROLE_FILE"
