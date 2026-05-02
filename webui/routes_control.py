from urllib.parse import parse_qs
from pathlib import Path
import json
from datetime import datetime
import urllib.request


def handle_control_post(handler, parsed):
    if parsed.path != '/api/control/ingest':
        return None
    ra = handler.client_address[0] if handler.client_address else ''
    if not handler.control_ingest_authorized(handler.headers, ra):
        return handler._json({'ok': False, 'error': 'unauthorized'}, code=403)
    try:
        length = int(handler.headers.get('Content-Length', '0'))
        raw = handler.rfile.read(length) if length > 0 else b'{}'
        body = json.loads(raw.decode('utf-8', errors='replace'))
        if not isinstance(body, dict):
            raise ValueError('body must be object')
        rxs_id = str(body.get('rxs_id', '')).strip().upper()
        if not handler._is_valid_rxs_id(rxs_id):
            return handler._json({'ok': False, 'error': 'invalid_rxs_id'}, code=400)
        pol = handler.load_control_plane_policy()
        max_events = max(1, min(int(pol.get('maxEventsPerIngest', 5000)), 20000))
        events = body.get('events', [])
        if not isinstance(events, list):
            events = []
        events = events[:max_events]
        heartbeat = body.get('heartbeat', {}) if isinstance(body.get('heartbeat', {}), dict) else {}
        stats = body.get('stats', {}) if isinstance(body.get('stats', {}), dict) else {}
        rec = {
            'ts': datetime.utcnow().isoformat() + 'Z',
            'rxs_id': rxs_id,
            'remote_addr': ra,
            'events': events,
            'event_count': len(events),
            'heartbeat': heartbeat,
            'stats': stats,
        }
        base, latest_dir, by_rx = handler._control_ingest_paths()
        day = datetime.utcnow().strftime('%Y-%m-%d')
        out = by_rx / f'{rxs_id}_{day}.jsonl'
        with out.open('a', encoding='utf-8') as f:
            f.write(json.dumps(rec) + '\n')
        (latest_dir / f'{rxs_id}.json').write_text(json.dumps(rec, indent=2) + '\n', encoding='utf-8')
        return handler._json({'ok': True, 'rxs_id': rxs_id, 'event_count': len(events), 'path': str(out)})
    except Exception as e:
        return handler._json({'ok': False, 'error': str(e)}, code=400)


def handle_control_get(handler, parsed):
    if parsed.path == '/api/control/policy':
        pol = handler.load_control_plane_policy()
        pol.pop('ingestToken', None)
        return handler._json(pol)

    if parsed.path == '/api/control/state_summary':
        return handler._json(handler._control_state_summary())

    if parsed.path == '/api/control/receivers':
        _, latest_dir, _ = handler._control_ingest_paths()
        rows = []
        for p in sorted(latest_dir.glob('*.json')):
            try:
                d = json.loads(p.read_text(encoding='utf-8', errors='replace'))
                rows.append({
                    'rxs_id': str(d.get('rxs_id', '')).strip().upper(),
                    'last_ts': d.get('ts', ''),
                    'event_count': int(d.get('event_count', 0) or 0),
                    'heartbeat': d.get('heartbeat', {}),
                    'stats': d.get('stats', {}),
                })
            except Exception:
                pass
        return handler._json({'receivers': rows, 'count': len(rows)})

    if parsed.path == '/api/control/receiver_latest':
        q = parse_qs(parsed.query)
        rxs_id = str((q.get('rxs_id', [''])[0] or '')).strip().upper()
        if not handler._is_valid_rxs_id(rxs_id):
            return handler._json({'ok': False, 'error': 'invalid_rxs_id'}, code=400)
        _, latest_dir, _ = handler._control_ingest_paths()
        p = latest_dir / f'{rxs_id}.json'
        if not p.exists():
            return handler._json({'ok': False, 'error': 'not_found'}, code=404)
        try:
            d = json.loads(p.read_text(encoding='utf-8', errors='replace'))
            return handler._json({'ok': True, 'data': d})
        except Exception as e:
            return handler._json({'ok': False, 'error': str(e)}, code=500)

    if parsed.path == '/api/receiver_proxy':
        q = parse_qs(parsed.query)
        rxs_id = str((q.get('rxs_id', [''])[0] or '')).strip().upper()
        subpath = str((q.get('path', [''])[0] or '')).strip()
        if not handler._is_valid_rxs_id(rxs_id):
            return handler._json({'ok': False, 'error': 'invalid_rxs_id'}, code=400)
        if not subpath.startswith('/api/'):
            return handler._json({'ok': False, 'error': 'path_must_start_api'}, code=400)
        reg = handler._load_receivers_registry()
        rx = next((r for r in (reg.get('receivers') or []) if str(r.get('rxs_id', '')).strip().upper() == rxs_id), None)
        if not rx:
            return handler._json({'ok': False, 'error': 'receiver_not_found'}, code=404)
        base = str(rx.get('base_url', 'local') or 'local').strip()
        if base in ('', 'local'):
            return handler._json({'ok': False, 'error': 'receiver_is_local_use_direct'}, code=400)
        try:
            url = base.rstrip('/') + subpath
            with urllib.request.urlopen(url, timeout=10) as resp:
                raw = resp.read().decode('utf-8', errors='replace')
            try:
                obj = json.loads(raw)
            except Exception:
                obj = {'raw': raw}
            return handler._json({'ok': True, 'rxs_id': rxs_id, 'path': subpath, 'data': obj})
        except Exception as e:
            return handler._json({'ok': False, 'error': str(e)}, code=502)

    return None
