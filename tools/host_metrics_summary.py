#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


METRICS = [
    'cpu_percent',
    'mem_percent',
    'disk_percent',
    'temp_c',
    'load_1m_per_core',
]


def pct(values, p):
    if not values:
        return None
    values = sorted(values)
    idx = int((len(values) - 1) * p)
    return values[idx]


def main():
    ap = argparse.ArgumentParser(description='Summarize FW-LAB host_metrics JSONL')
    ap.add_argument('--jsonl', required=True)
    ap.add_argument('--out', default='')
    args = ap.parse_args()

    path = Path(args.jsonl)
    rows = []
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except Exception:
            continue
        if isinstance(ev, dict):
            rows.append(ev)

    summary = {
        'schema': 'alert.host.metrics.summary.v1',
        'source': str(path),
        'samples': len(rows),
        'status_counts': {'ok': 0, 'warn': 0},
        'breach_counts': {},
        'metrics': {},
    }

    for ev in rows:
        status = ev.get('status', 'ok')
        summary['status_counts'][status] = summary['status_counts'].get(status, 0) + 1
        for b in ev.get('breaches', []) or []:
            m = b.get('metric', 'unknown')
            summary['breach_counts'][m] = summary['breach_counts'].get(m, 0) + 1

    for m in METRICS:
        vals = []
        for ev in rows:
            v = (ev.get('metrics') or {}).get(m)
            if isinstance(v, (int, float)):
                vals.append(float(v))
        if not vals:
            continue
        summary['metrics'][m] = {
            'min': round(min(vals), 3),
            'max': round(max(vals), 3),
            'avg': round(sum(vals) / len(vals), 3),
            'p95': round(pct(vals, 0.95), 3),
        }

    text = json.dumps(summary, indent=2)
    if args.out:
        Path(args.out).write_text(text + '\n', encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
