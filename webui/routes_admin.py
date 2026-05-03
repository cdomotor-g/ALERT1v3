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
