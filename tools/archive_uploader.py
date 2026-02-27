#!/usr/bin/env python3
import argparse
import gzip
import hashlib
import json
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


def first_last_ts(lines):
    first = None
    last = None
    for line in lines:
        try:
            obj = json.loads(line)
            ts = obj.get('ts')
            if ts:
                if first is None:
                    first = ts
                last = ts
        except Exception:
            continue
    return first, last


def chunk_source_file(src: Path, state_dir: Path, max_lines: int, max_bytes: int, dry_run: bool):
    chunks_dir = state_dir / 'chunks'
    chunks_dir.mkdir(parents=True, exist_ok=True)

    created = []
    chunk_idx = 0
    current_lines = []
    current_bytes = 0

    def flush_chunk():
        nonlocal chunk_idx, current_lines, current_bytes
        if not current_lines:
            return
        chunk_idx += 1
        ts = int(time.time())
        stem = src.name.replace('.jsonl', '')
        out = chunks_dir / f'{stem}.part{chunk_idx:04d}.{ts}.jsonl.gz'
        event_count = len(current_lines)
        first_ts, last_ts = first_last_ts(current_lines)

        if not dry_run:
            with gzip.open(out, 'wt', encoding='utf-8') as gz:
                gz.writelines(current_lines)
            entry = {
                'source_path': str(src),
                'chunk_path': str(out),
                'chunk_sha256': sha256_file(out),
                'chunk_size_bytes': out.stat().st_size,
                'event_count': event_count,
                'first_ts': first_ts,
                'last_ts': last_ts,
                'status': 'pending',
                'created_at': int(time.time()),
            }
        else:
            entry = {
                'source_path': str(src),
                'chunk_path': str(out),
                'event_count': event_count,
                'first_ts': first_ts,
                'last_ts': last_ts,
                'status': 'pending',
                'created_at': int(time.time()),
            }

        created.append(entry)
        current_lines = []
        current_bytes = 0

    with src.open('r', encoding='utf-8', errors='replace') as f:
        for line in f:
            if not line.strip():
                continue
            b = len(line.encode('utf-8', errors='replace'))
            if current_lines and (len(current_lines) >= max_lines or current_bytes + b > max_bytes):
                flush_chunk()
            current_lines.append(line)
            current_bytes += b

    flush_chunk()
    return created


def main():
    ap = argparse.ArgumentParser(description='FW-LAB archive uploader scaffold')
    ap.add_argument('--policy', default='config/archive_policy.json')
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    policy_path = Path(args.policy)
    policy = load_json(policy_path, {})
    roots = policy.get('sourceRoots', ['/home/cdomotor/rf_log'])
    state_dir = Path(policy.get('stateDir', 'rf_log/archive_state'))
    chunk_cfg = policy.get('chunk', {})
    max_lines = int(chunk_cfg.get('maxLines', 50000))
    max_bytes = int(chunk_cfg.get('maxBytes', 20 * 1024 * 1024))

    manifest_path = state_dir / 'manifest.json'
    manifest = load_json(manifest_path, {'entries': []})

    source_state_path = state_dir / 'source_state.json'
    source_state = load_json(source_state_path, {'processed_files': []})
    done = set(source_state.get('processed_files', []))

    candidates = [f for f in discover_jsonl(roots) if str(f) not in done]

    new_entries = []
    for src in candidates:
        entries = chunk_source_file(src, state_dir, max_lines=max_lines, max_bytes=max_bytes, dry_run=args.dry_run)
        new_entries.extend(entries)
        done.add(str(src))

    if not args.dry_run:
        manifest.setdefault('entries', []).extend(new_entries)
        save_json(manifest_path, manifest)
        save_json(source_state_path, {'processed_files': sorted(done)})

    print(json.dumps({
        'schema': 'alert.archive.uploader.run.v1',
        'policy': str(policy_path),
        'dry_run': args.dry_run,
        'sources_processed': len(candidates),
        'new_entries': len(new_entries),
        'manifest': str(manifest_path),
        'source_state': str(source_state_path),
    }))


if __name__ == '__main__':
    main()
