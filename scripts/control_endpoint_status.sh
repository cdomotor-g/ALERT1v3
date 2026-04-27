#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CFG="$ROOT/config/control_plane_endpoints.json"

python3 - "$CFG" <<'PY'
import json, sys
from pathlib import Path
p=Path(sys.argv[1])
if not p.exists():
    raise SystemExit(f"missing {p}")
d=json.loads(p.read_text(encoding='utf-8'))
print('activeBaseUrl:', d.get('activeBaseUrl',''))
print('ingestPath   :', d.get('ingestPath','/api/control/ingest'))
print('statusPath   :', d.get('statusPath','/api/control/policy'))
print('candidates   :')
for k,v in (d.get('candidates') or {}).items():
    print(f'  - {k}: {v}')
PY
