#!/usr/bin/env python3
import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path


def load_events(path):
    events = []
    if not path.exists():
        return events
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
            if isinstance(ev, dict):
                events.append(ev)
        except Exception:
            pass
    return events


def parse_ts(s):
    try:
        return datetime.fromisoformat(s.replace('Z', '+00:00'))
    except Exception:
        return None


def summarize_events(events):
    out = {
        'events_total': len(events),
        'status_counts': Counter(),
        'error_code_counts': Counter(),
        'confidence_counts': Counter(),
        'score_avg': None,
        'score_min': None,
        'score_max': None,
        'decode_rate_per_min': 0.0,
        'time_window_seconds': 0.0,
    }
    if not events:
        return out

    scores = []
    ts = []
    for ev in events:
        out['status_counts'][ev.get('status', 'unknown')] += 1
        q = ev.get('quality') or {}
        c = q.get('confidence')
        if c:
            out['confidence_counts'][c] += 1
        s = q.get('score')
        if isinstance(s, (int, float)):
            scores.append(float(s))
        for er in (ev.get('errors') or []):
            out['error_code_counts'][er.get('code', 'unknown')] += 1
        t = parse_ts(ev.get('ts', ''))
        if t:
            ts.append(t)

    if scores:
        out['score_avg'] = round(sum(scores) / len(scores), 4)
        out['score_min'] = round(min(scores), 4)
        out['score_max'] = round(max(scores), 4)

    if len(ts) >= 2:
        span = (max(ts) - min(ts)).total_seconds()
        out['time_window_seconds'] = round(span, 2)
        out['decode_rate_per_min'] = round((len(events) / span) * 60.0, 3) if span > 0 else 0.0

    out['status_counts'] = dict(out['status_counts'])
    out['error_code_counts'] = dict(out['error_code_counts'])
    out['confidence_counts'] = dict(out['confidence_counts'])
    return out


def main():
    ap = argparse.ArgumentParser(description='FW-LAB soak report generator')
    ap.add_argument('--events-jsonl', required=True)
    ap.add_argument('--host-metrics-jsonl', default='')
    ap.add_argument('--out', required=True)
    args = ap.parse_args()

    events_path = Path(args.events_jsonl)
    events = load_events(events_path)
    rep = {
        'schema': 'alert.soak.report.v1',
        'generated_at': datetime.utcnow().isoformat() + 'Z',
        'inputs': {
            'events_jsonl': str(events_path),
            'host_metrics_jsonl': args.host_metrics_jsonl,
        },
        'decoder': summarize_events(events),
    }

    if args.host_metrics_jsonl:
        hm = load_events(Path(args.host_metrics_jsonl))
        rep['host_metrics'] = {
            'samples': len(hm),
            'warn_samples': sum(1 for x in hm if x.get('status') == 'warn'),
        }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=2) + '\n', encoding='utf-8')
    print(out)


if __name__ == '__main__':
    main()
