#!/usr/bin/env python3
import argparse
import os
import time
from pathlib import Path


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
    kept = []
    for f in files:
        age = file_age_days(f, now)
        if age > max_days:
            deleted.append((f, age))
            if not dry_run:
                try:
                    f.unlink(missing_ok=True)
                except Exception:
                    pass
        else:
            kept.append((f, age))
    return deleted, kept


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


def main():
    ap = argparse.ArgumentParser(description='FW-LAB log retention cleanup')
    ap.add_argument('--root', action='append', default=['/home/cdomotor/rf_log', '/home/cdomotor/.openclaw/workspace/projects/ALERT1v3/rf_log'], help='Log root (repeatable)')
    ap.add_argument('--days', type=float, default=14, help='Delete files older than this many days')
    ap.add_argument('--max-mb', type=float, default=1024, help='Target max total MB for matching files across roots')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    patterns = ['*.jsonl', '*.csv', '*.log']
    now = time.time()
    files = collect_files(args.root, patterns)

    old_deleted, _ = enforce_days(files, args.days, now, args.dry_run)
    files2 = collect_files(args.root, patterns)
    size_deleted, remaining = enforce_size(files2, parse_size_mb(args.max_mb), args.dry_run)

    print(f'dry_run={args.dry_run}')
    print(f'roots={args.root}')
    print(f'policy_days={args.days} policy_max_mb={args.max_mb}')
    print(f'deleted_by_age={len(old_deleted)} deleted_by_size={len(size_deleted)} remaining_bytes={remaining}')


if __name__ == '__main__':
    main()
