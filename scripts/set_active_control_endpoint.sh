#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CFG="$ROOT/config/control_plane_endpoints.json"
TARGET="${1:-}"

usage(){
  cat <<EOF
Usage: $0 <candidate-name|https://base-url>

Updates config/control_plane_endpoints.json activeBaseUrl.
If TARGET matches a candidate key, that URL is used.
EOF
}

[[ -n "$TARGET" ]] || { usage; exit 2; }
[[ "$TARGET" =~ ^(-h|--help)$ ]] && { usage; exit 0; }

python3 - "$CFG" "$TARGET" <<'PY'
import json, sys
from pathlib import Path
cfg=Path(sys.argv[1])
target=sys.argv[2].strip()
if not cfg.exists():
    raise SystemExit(f"missing {cfg}")
d=json.loads(cfg.read_text(encoding='utf-8'))
cands=d.get('candidates') or {}
if target in cands:
    url=str(cands[target]).strip()
else:
    url=target
if not (url.startswith('http://') or url.startswith('https://')):
    raise SystemExit('target must be candidate key or absolute http(s) url')
d['activeBaseUrl']=url.rstrip('/')
cfg.write_text(json.dumps(d, indent=2)+'\n', encoding='utf-8')
print('activeBaseUrl ->', d['activeBaseUrl'])
PY
