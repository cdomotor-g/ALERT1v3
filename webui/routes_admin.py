import json
from pathlib import Path
from urllib.parse import parse_qs


def _admin_gate(handler, parsed):
    ra = handler.client_address[0] if handler.client_address else ''
    if not handler.admin_authorized(handler.headers, ra):
        handler.audit_admin_action(parsed.path, ra, False, {'error': 'unauthorized'})
        handler._json({'ok': False, 'error': 'unauthorized'}, code=403)
        return False, ra
    return True, ra


def handle_admin_post(handler, parsed):
    if parsed.path not in ['/api/admin/storage_policy', '/api/admin/rf_control', '/api/admin/receiver_action', '/api/admin/meta/catalog']:
        return None
    ok, ra = _admin_gate(handler, parsed)
    if not ok:
        return True
    try:
        length = int(handler.headers.get('Content-Length', '0'))
        raw = handler.rfile.read(length) if length > 0 else b'{}'
        body = json.loads(raw.decode('utf-8'))
        if not isinstance(body, dict):
            raise ValueError('body must be object')

        if parsed.path == '/api/admin/storage_policy':
            current = handler.load_storage_policy()
            merged = {
                'localRetentionDays': body.get('localRetentionDays', current.get('localRetentionDays', 2)),
                'maxLocalMb': body.get('maxLocalMb', current.get('maxLocalMb', 1024)),
                'thresholds': {
                    'warnDiskPercent': (body.get('thresholds') or {}).get('warnDiskPercent', (current.get('thresholds') or {}).get('warnDiskPercent', 85)),
                    'criticalDiskPercent': (body.get('thresholds') or {}).get('criticalDiskPercent', (current.get('thresholds') or {}).get('criticalDiskPercent', 92)),
                    'emergencyDiskPercent': (body.get('thresholds') or {}).get('emergencyDiskPercent', (current.get('thresholds') or {}).get('emergencyDiskPercent', 96)),
                },
                'criticalPolicy': {
                    'criticalRetentionDays': (body.get('criticalPolicy') or {}).get('criticalRetentionDays', (current.get('criticalPolicy') or {}).get('criticalRetentionDays', 1)),
                    'emergencyRetentionHours': (body.get('criticalPolicy') or {}).get('emergencyRetentionHours', (current.get('criticalPolicy') or {}).get('emergencyRetentionHours', 12)),
                },
            }
            handler.save_storage_policy(merged)
            handler.audit_admin_action(parsed.path, ra, True, {'keys': ['storage_policy']})
            handler._json({'ok': True, 'policy': merged})
            return True

        if parsed.path == '/api/admin/rf_control':
            current = handler.load_rf_control()
            merged = {
                'center_freq_hz': body.get('center_freq_hz', current.get('center_freq_hz', 173900000.0)),
                'rf_gain_db': body.get('rf_gain_db', current.get('rf_gain_db', 40.0)),
                'rf_squelch_db': body.get('rf_squelch_db', current.get('rf_squelch_db', -33.0)),
            }
            handler.save_rf_control(merged)
            handler.audit_admin_action(parsed.path, ra, True, {'keys': ['rf_control']})
            handler._json({'ok': True, 'rf_control': merged})
            return True

        if parsed.path == '/api/admin/meta/catalog':
            cat = handler.load_meta_catalog()
            entity = str(body.get('entity', '')).strip().lower()
            op = str(body.get('op', '')).strip().lower()
            item = body.get('item', {}) or {}
            if entity not in ('station', 'sensor') or op not in ('upsert', 'delete'):
                handler._json({'ok': False, 'error': 'invalid entity/op'}, code=400)
                return True
            key_field = 'station_key' if entity == 'station' else 'sensor_key'
            key = str(item.get(key_field, body.get(key_field, ''))).strip()
            arr = cat['stations'] if entity == 'station' else cat['sensors']
            idx = next((i for i, r in enumerate(arr) if str(r.get(key_field, '')).strip() == key), -1)
            if op == 'delete':
                if idx >= 0:
                    arr.pop(idx)
                snap = handler.snapshot_meta_catalog(cat, f'{entity}_delete')
                handler.save_meta_catalog(cat)
                handler.meta_history_append('delete', {'entity': entity, key_field: key, 'snapshot': snap})
                handler.audit_admin_action(parsed.path, ra, True, {'entity': entity, 'op': op, key_field: key})
                handler._json({'ok': True, 'entity': entity, 'op': op, key_field: key, 'snapshot': snap})
                return True
            if not key:
                handler._json({'ok': False, 'error': f'missing {key_field}'}, code=400)
                return True
            if idx >= 0:
                arr[idx].update(item)
            else:
                arr.append(item)
            snap = handler.snapshot_meta_catalog(cat, f'{entity}_upsert')
            handler.save_meta_catalog(cat)
            handler.meta_history_append('upsert', {'entity': entity, key_field: key, 'snapshot': snap})
            handler.audit_admin_action(parsed.path, ra, True, {'entity': entity, 'op': op, key_field: key})
            handler._json({'ok': True, 'entity': entity, 'op': op, key_field: key, 'snapshot': snap})
            return True

        action = str(body.get('action', '')).strip().lower()
        if action not in ('start', 'stop', 'restart'):
            handler._json({'ok': False, 'error': 'invalid action'}, code=400)
            return True
        cp = handler.subprocess_run(['sudo', 'systemctl', action, 'fwlab-receiver.service'])
        if cp.returncode != 0:
            err = cp.stderr.strip() or cp.stdout.strip()
            handler.audit_admin_action(parsed.path, ra, False, {'action': action, 'error': err})
            handler._json({'ok': False, 'error': err}, code=500)
            return True
        handler.audit_admin_action(parsed.path, ra, True, {'action': action})
        handler._json({'ok': True, 'action': action})
        return True
    except Exception as e:
        handler.audit_admin_action(parsed.path, ra, False, {'error': str(e)})
        handler._json({'ok': False, 'error': str(e)}, code=400)
        return True


def handle_admin_get(handler, parsed):
    if parsed.path == '/api/admin/storage_policy':
        ok, ra = _admin_gate(handler, parsed)
        if not ok:
            return True
        handler.audit_admin_action(parsed.path, ra, True, {})
        handler._json(handler.load_storage_policy())
        return True

    if parsed.path == '/api/admin/rf_control':
        ok, ra = _admin_gate(handler, parsed)
        if not ok:
            return True
        handler.audit_admin_action(parsed.path, ra, True, {})
        handler._json(handler.load_rf_control())
        return True

    if parsed.path == '/api/admin/audit_recent':
        ok, ra = _admin_gate(handler, parsed)
        if not ok:
            return True
        q = parse_qs(parsed.query)
        limit = int(q.get('limit', ['100'])[0])
        limit = max(1, min(limit, 500))
        p = Path('rf_log/audit/admin_actions.jsonl')
        rows = []
        if p.exists():
            for line in p.read_text(encoding='utf-8', errors='replace').splitlines()[-limit:]:
                if not line.strip():
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
        handler.audit_admin_action(parsed.path, ra, True, {'limit': limit})
        handler._json({'events': rows, 'count': len(rows)})
        return True

    if parsed.path == '/api/admin/meta/history':
        ok, ra = _admin_gate(handler, parsed)
        if not ok:
            return True
        q = parse_qs(parsed.query)
        limit = int(q.get('limit', ['100'])[0])
        limit = max(1, min(limit, 500))
        p = Path('rf_log/audit/meta_catalog_history.jsonl')
        rows = []
        if p.exists():
            for line in p.read_text(encoding='utf-8', errors='replace').splitlines()[-limit:]:
                if not line.strip():
                    continue
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
        handler.audit_admin_action(parsed.path, ra, True, {'limit': limit})
        handler._json({'events': rows, 'count': len(rows)})
        return True

    return None
