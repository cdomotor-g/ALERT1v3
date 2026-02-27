#!/usr/bin/env python3
import argparse
import gzip
import hashlib
import json
from pathlib import Path


def sha256_file(path: Path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def validate_entry(entry):
    cp = Path(entry.get('chunk_path', ''))
    res = {
        'chunk_path': str(cp),
        'exists': cp.exists(),
        'sha_ok': None,
        'gzip_ok': None,
        'event_count_ok': None,
        'first_ts_ok': None,
        'last_ts_ok': None,
        'error': None,
    }

    if not cp.exists():
        res['error'] = 'missing_chunk'
        return res

    try:
        expected = entry.get('chunk_sha256')
        if expected:
            res['sha_ok'] = (sha256_file(cp) == expected)

        lines = []
        with gzip.open(cp, 'rt', encoding='utf-8', errors='replace') as gz:
            for line in gz:
                if line.strip():
                    lines.append(line)
        res['gzip_ok'] = True

        count = len(lines)
        ec = entry.get('event_count')
        if ec is not None:
            res['event_count_ok'] = (int(ec) == count)

        first_ts = None
        last_ts = None
        for line in lines:
            try:
                obj = json.loads(line)
                ts = obj.get('ts')
                if ts:
                    if first_ts is None:
                        first_ts = ts
                    last_ts = ts
            except Exception:
                continue

        if entry.get('first_ts') is not None:
            res['first_ts_ok'] = (entry.get('first_ts') == first_ts)
        if entry.get('last_ts') is not None:
            res['last_ts_ok'] = (entry.get('last_ts') == last_ts)

    except Exception as e:
        res['gzip_ok'] = False
        res['error'] = str(e)

    return res


def main():
    ap = argparse.ArgumentParser(description='Validate archive restore path from local manifest/chunks')
    ap.add_argument('--manifest', default='rf_log/archive_state/manifest.json')
    ap.add_argument('--limit', type=int, default=20)
    ap.add_argument('--out', default='')
    args = ap.parse_args()

    mpath = Path(args.manifest)
    if not mpath.exists():
        raise SystemExit(f'manifest missing: {mpath}')

    manifest = json.loads(mpath.read_text(encoding='utf-8'))
    entries = manifest.get('entries', [])[-max(1, args.limit):]

    results = [validate_entry(e) for e in entries]

    summary = {
        'schema': 'alert.archive.restore.check.v1',
        'manifest': str(mpath),
        'checked': len(results),
        'ok': sum(1 for r in results if all(
            (r.get('exists') is True,
             r.get('gzip_ok') in (True, None),
             r.get('sha_ok') in (True, None),
             r.get('event_count_ok') in (True, None),
             r.get('first_ts_ok') in (True, None),
             r.get('last_ts_ok') in (True, None))
        )),
        'failed': 0,
        'results': results,
    }
    summary['failed'] = summary['checked'] - summary['ok']

    txt = json.dumps(summary, indent=2)
    if args.out:
        Path(args.out).write_text(txt + '\n', encoding='utf-8')
    print(txt)


if __name__ == '__main__':
    main()
