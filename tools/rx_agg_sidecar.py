#!/usr/bin/env python3
import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path


def parse_ts(ts: str):
    try:
        if ts.endswith('Z'):
            ts = ts[:-1] + '+00:00'
        return datetime.fromisoformat(ts).timestamp()
    except Exception:
        return None


def bin_start(ts_s: float, width_s: int, phase_s: int = 0) -> int:
    return int(((ts_s - phase_s) // width_s) * width_s + phase_s)


def load_events(paths):
    out = []
    for p in paths:
        try:
            for ln in p.read_text(encoding='utf-8', errors='replace').splitlines():
                try:
                    ev = json.loads(ln)
                except Exception:
                    continue
                ts = parse_ts(str(ev.get('ts', '')))
                if ts is not None:
                    out.append(ts)
        except Exception:
            continue
    return out


def build_bins(ts_list, now_s):
    # 30m chart: 24h window, 30m bins, phase at :15/:45
    width_30 = 30 * 60
    phase_30 = 15 * 60
    bins30_n = 48
    end30 = bin_start(now_s, width_30, phase_30)
    starts30 = [end30 - (bins30_n - 1 - i) * width_30 for i in range(bins30_n)]
    counts30 = {s: 0 for s in starts30}

    # 2m chart: 30m window, 2m bins
    width_2 = 2 * 60
    bins2_n = 15
    end2 = bin_start(now_s, width_2, 0)
    starts2 = [end2 - (bins2_n - 1 - i) * width_2 for i in range(bins2_n)]
    counts2 = {s: 0 for s in starts2}

    min2, min30 = starts2[0], starts30[0]
    for ts in ts_list:
        if ts >= min2:
            b = bin_start(ts, width_2, 0)
            if b in counts2:
                counts2[b] += 1
        if ts >= min30:
            b = bin_start(ts, width_30, phase_30)
            if b in counts30:
                counts30[b] += 1

    def label_age(starts, now):
        labels = []
        for i, s in enumerate(starts):
            age_s = max(0, now - s)
            if len(starts) == bins30_n:
                labels.append('now' if i == len(starts) - 1 else f"-{int(round(age_s/3600))}h")
            else:
                labels.append('now' if i == len(starts) - 1 else f"-{int(round(age_s/60))}m")
        return labels

    return {
        'ts': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
        'rx_2m_30m': {
            'labels': label_age(starts2, now_s),
            'counts': [counts2[s] for s in starts2],
        },
        'rx_30m_24h': {
            'labels': label_age(starts30, now_s),
            'counts': [counts30[s] for s in starts30],
            'phase_minutes': 15,
        },
    }


def main():
    ap = argparse.ArgumentParser()
    default_log_dir = os.environ.get('FWLAB_LOG_BASE', str(Path.home() / 'rf_log'))
    default_out = os.environ.get('FWLAB_RX_AGG_OUT', str(Path(__file__).resolve().parents[1] / 'rf_log' / 'rx_agg.json'))
    ap.add_argument('--log-dir', default=default_log_dir)
    ap.add_argument('--out', default=default_out)
    ap.add_argument('--interval', type=float, default=10.0)
    args = ap.parse_args()

    log_dir = Path(args.log_dir)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    while True:
        now_s = time.time()
        # read recent files only (today + yesterday dirs typically)
        files = sorted(log_dir.glob('*/rx_events_*.jsonl'))[-8:]
        ts_list = load_events(files)
        payload = build_bins(ts_list, now_s)
        payload['source_files'] = [str(p) for p in files]
        out_path.write_text(json.dumps(payload), encoding='utf-8')
        time.sleep(max(2.0, args.interval))


if __name__ == '__main__':
    main()
