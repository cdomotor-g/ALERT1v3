#!/usr/bin/env python3
import argparse
import json
import shutil
import time
from pathlib import Path


DEFAULT_ROOTS = ['/home/cdomotor/rf_log', '/home/cdomotor/.openclaw/workspace/projects/ALERT1v3/rf_log']


def file_age_days(path: Path, now: float) -> float:
    return (now - path.stat().st_mtime) / 86400.0


def collect_files(roots, patterns):
    out = []
    for root in roots:
        r = Path(root)
        if not r.exists():
            continue
        for pat in patterns:
            out.extend(r.rglob(pat))
    return [p for p in out if p.is_file()]


def enforce_days(files, max_days, now, dry_run):
    deleted = []
    for f in files:
        age = file_age_days(f, now)
        if age > max_days:
            deleted.append((f, age))
            if not dry_run:
                try:
                    f.unlink(missing_ok=True)
                except Exception:
                    pass
    return deleted


def enforce_size(files, max_bytes, dry_run):
    files = sorted(files, key=lambda p: p.stat().st_mtime)
    total = sum(p.stat().st_size for p in files)
    deleted = []
    if total <= max_bytes:
        return deleted, total
    for f in files:
        if total <= max_bytes:
            break
        size = f.stat().st_size
        deleted.append((f, size))
        if not dry_run:
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass
        total -= size
    return deleted, total


def parse_size_mb(v):
    return int(float(v) * 1024 * 1024)


def load_policy(path: str):
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except Exception:
        return {}


def disk_percent(path='/'):
    d = shutil.disk_usage(path)
    return (100.0 * d.used / d.total) if d.total else 0.0


def main():
    ap = argparse.ArgumentParser(description='FW-LAB log retention cleanup')
    ap.add_argument('--policy', default='config/storage_policy.json')
    ap.add_argument('--root', action='append', default=[])
    ap.add_argument('--days', type=float, default=None)
    ap.add_argument('--max-mb', type=float, default=None)
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    policy = load_policy(args.policy)
    roots = args.root or DEFAULT_ROOTS

    local_days = float(args.days if args.days is not None else policy.get('localRetentionDays', 2))
    max_mb = float(args.max_mb if args.max_mb is not None else policy.get('maxLocalMb', 1024))

    th = policy.get('thresholds', {})
    warn_pct = float(th.get('warnDiskPercent', 85))
    critical_pct = float(th.get('criticalDiskPercent', 92))
    emergency_pct = float(th.get('emergencyDiskPercent', 96))

    crit = policy.get('criticalPolicy', {})
    critical_days = float(crit.get('criticalRetentionDays', 1))
    emergency_hours = float(crit.get('emergencyRetentionHours', 12))

    used_pct = disk_percent('/')
    mode = 'normal'
    effective_days = local_days
    if used_pct >= emergency_pct:
        mode = 'emergency'
        effective_days = emergency_hours / 24.0
    elif used_pct >= critical_pct:
        mode = 'critical'
        effective_days = critical_days
    elif used_pct >= warn_pct:
        mode = 'warn'

    patterns = ['*.jsonl', '*.csv', '*.log']
    now = time.time()
    files = collect_files(roots, patterns)

    deleted_age = enforce_days(files, effective_days, now, args.dry_run)
    files2 = collect_files(roots, patterns)

    effective_max_mb = max_mb
    if mode == 'critical':
        effective_max_mb = min(max_mb, max_mb * 0.5)
    elif mode == 'emergency':
        effective_max_mb = min(max_mb, max_mb * 0.25)

    deleted_size, remaining = enforce_size(files2, parse_size_mb(effective_max_mb), args.dry_run)

    out = {
        'schema': 'alert.storage.retention.run.v1',
        'dry_run': args.dry_run,
        'roots': roots,
        'disk_used_percent': round(used_pct, 3),
        'mode': mode,
        'policy_days': local_days,
        'effective_days': round(effective_days, 3),
        'policy_max_mb': max_mb,
        'effective_max_mb': round(effective_max_mb, 3),
        'deleted_by_age': len(deleted_age),
        'deleted_by_size': len(deleted_size),
        'remaining_bytes': remaining,
    }
    print(json.dumps(out))


if __name__ == '__main__':
    main()
