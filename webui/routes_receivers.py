import json


def handle_receivers_post(handler, parsed):
    if parsed.path != '/api/receivers_registry_update':
        return None
    try:
        length = int(handler.headers.get('Content-Length', '0'))
        raw = handler.rfile.read(length) if length > 0 else b'{}'
        body = json.loads(raw.decode('utf-8', errors='replace'))
        op = str(body.get('op', 'upsert')).strip().lower()  # upsert|delete
        item = body.get('item', {}) or {}
        rxs_id = str(item.get('rxs_id', body.get('rxs_id', ''))).strip().upper()
        if not handler._is_valid_rxs_id(rxs_id):
            return handler._json({'ok': False, 'error': 'invalid_rxs_id'}, code=400)
        reg = handler._load_receivers_registry()
        rows = reg.get('receivers', []) or []
        idx = next((i for i, r in enumerate(rows) if str(r.get('rxs_id', '')).strip().upper() == rxs_id), -1)
        if op == 'delete':
            if idx >= 0:
                rows.pop(idx)
            reg['receivers'] = rows
            handler.RECEIVERS_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
            handler.RECEIVERS_REGISTRY_PATH.write_text(json.dumps(reg, indent=2) + '\n', encoding='utf-8')
            return handler._json({'ok': True, 'op': 'delete', 'rxs_id': rxs_id})

        rec = {
            'rxs_id': rxs_id,
            'name': str(item.get('name', '')).strip() or f'RX {rxs_id}',
            'location': str(item.get('location', '')).strip(),
            'base_url': str(item.get('base_url', 'local')).strip() or 'local',
            'status': str(item.get('status', '')).strip(),
        }
        if idx >= 0:
            rows[idx].update(rec)
        else:
            rows.append(rec)
        reg['receivers'] = rows
        handler.RECEIVERS_REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
        handler.RECEIVERS_REGISTRY_PATH.write_text(json.dumps(reg, indent=2) + '\n', encoding='utf-8')
        return handler._json({'ok': True, 'op': 'upsert', 'rxs_id': rxs_id})
    except Exception as e:
        return handler._json({'ok': False, 'error': str(e)}, code=400)
