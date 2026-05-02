from urllib.parse import parse_qs
from pathlib import Path
import json


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

    return None
