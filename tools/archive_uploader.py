#!/usr/bin/env python3
import argparse
import gzip
import hashlib
import json
import os
import time
from pathlib import Path


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return default


def save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def sha256_file(path: Path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def discover_jsonl(roots):
    files = []
    for r in roots:
        p = Path(r)
        if not p.exists():
            continue
        files.extend(sorted(p.rglob('rx_events_*.jsonl')))
    return [f for f in files if f.is_file()]


def compress_to_state(src: Path, state_dir: Path):
    rel = src.as_posix().replace('/', '_')
    ts = int(time.time())
    out = state_dir / 'chunks' / f'{rel}.{ts}.jsonl.gz'
    out.parent.mkdir(parents=True, exist_ok=True)
    with src.open('rb') as fin, gzip.open(out, 'wb') as fout:
        fout.writelines(fin)
    return out


def main():
    ap = argparse.ArgumentParser(description='FW-LAB archive uploader scaffold')
    ap.add_argument('--policy', default='config/archive_policy.json')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    policy_path = Path(args.policy)
    policy = load_json(policy_path, {})
    roots = policy.get('sourceRoots', ['/home/cdomotor/rf_log'])
    state_dir = Path(policy.get('stateDir', 'rf_log/archive_state'))
    manifest_path = state_dir / 'manifest.json'
    manifest = load_json(manifest_path, {'entries': []})

    known_src = {e.get('source_path') for e in manifest.get('entries', [])}
    candidates = [f for f in discover_jsonl(roots) if str(f) not in known_src]

    added = 0
    for src in candidates:
        entry = {
            'source_path': str(src),
            'first_seen_ts': int(time.time()),
            'status': 'pending',
        }

        if not args.dry_run:
            gz = compress_to_state(src, state_dir)
            entry.update({
                'chunk_path': str(gz),
                'chunk_sha256': sha256_file(gz),
                'chunk_size_bytes': gz.stat().st_size,
            })

        manifest.setdefault('entries', []).append(entry)
        added += 1

    save_json(manifest_path, manifest)
    print(json.dumps({
        'schema': 'alert.archive.uploader.run.v1',
        'policy': str(policy_path),
        'dry_run': args.dry_run,
        'new_entries': added,
        'manifest': str(manifest_path),
    }))


if __name__ == '__main__':
    main()
