#!/usr/bin/env bash
set -euo pipefail

BASE="${BASE:-/home/cdomotor/.openclaw/workspace/projects/ALERT1v3}"
LOG_BASE="${LOG_BASE:-/home/cdomotor/rf_log}"
DATE_DIR="${DATE_DIR:-$(date +%F)}"
SECONDS_PER_CASE="${SECONDS_PER_CASE:-180}"
VALUES="${VALUES:-0.1256637061 0.2513274123 0.5026548246}"
OUT="${OUT:-$BASE/rf_log/sweep_symbol_sync_bw_$(date +%Y%m%d_%H%M%S).txt}"

mkdir -p "$(dirname "$OUT")"

echo "symbol_sync_bw sweep" | tee "$OUT"
echo "date_dir=$DATE_DIR seconds_per_case=$SECONDS_PER_CASE values=$VALUES" | tee -a "$OUT"

auto_write_demod(){
  local bw="$1"
  cat > "$BASE/config/demod_control.json" <<JSON
{
  "demod_mode": "afsk",
  "afsk_mark_hz": 2100.0,
  "afsk_space_hz": 1300.0,
  "symbol_sync_bw": $bw
}
JSON
}

ensure_decoder_baseline(){
  cat > "$BASE/config/decoder_control.json" <<JSON
{
  "invert_bits": true,
  "word_lsb_first": true,
  "enforce_fixed_pairs": true,
  "fixed_pair_hard_reject": false
}
JSON
}

summarize_case(){
  local bw="$1"
  local f="$2"
  python3 - <<PY
import json, statistics
f = "$f"
bw = "$bw"
try:
    lines = open(f, encoding='utf-8', errors='replace').read().splitlines()[-5000:]
except Exception:
    print(f"bw={bw},file={f},n=0,ok=0,warn=0,error=0,ones_median=None,top_errors=[]")
    raise SystemExit(0)
ok=warn=err=0
rat=[]
codes={}
for ln in lines:
    try:d=json.loads(ln)
    except:continue
    s=d.get('status')
    ok += 1 if s=='ok' else 0
    warn += 1 if s=='warn' else 0
    err += 1 if s=='error' else 0
    q=d.get('quality') or {}
    if isinstance(q.get('ones_ratio'), (int,float)):
        rat.append(float(q.get('ones_ratio')))
    for e in (d.get('errors') or []):
        c=e.get('code','?')
        codes[c]=codes.get(c,0)+1
med = round(statistics.median(rat), 4) if rat else None
top = sorted(codes.items(), key=lambda x:x[1], reverse=True)[:5]
print(f"bw={bw},file={f.split('/')[-1]},n={len(lines)},ok={ok},warn={warn},error={err},ones_median={med},top_errors={top}")
PY
}

ensure_decoder_baseline

for bw in $VALUES; do
  echo "\n=== case bw=$bw ===" | tee -a "$OUT"
  auto_write_demod "$bw"
  sudo systemctl restart fwlab-receiver
  sleep "$SECONDS_PER_CASE"
  f=$(ls -1t "$LOG_BASE/$DATE_DIR"/rx_events_*.jsonl 2>/dev/null | head -n1 || true)
  if [[ -z "$f" ]]; then
    echo "bw=$bw,file=NONE,n=0,ok=0,warn=0,error=0,ones_median=None,top_errors=[]" | tee -a "$OUT"
    continue
  fi
  summarize_case "$bw" "$f" | tee -a "$OUT"
done

echo "\nSweep complete: $OUT"
