from urllib.parse import parse_qs


def handle_events_get(handler, parsed):
    if parsed.path == '/api/events':
        q = parse_qs(parsed.query)
        limit = int(q.get('limit', ['100'])[0])
        limit = max(1, min(limit, 4000))
        handler.store.poll_new()
        events = list(handler.store.events)[-limit:]
        events = handler._with_sensor_mapping(events)
        return handler._json({'events': events, 'count': len(handler.store.events), 'source': str(handler.store.path)})

    if parsed.path == '/api/sensors':
        q = parse_qs(parsed.query)
        source_mode = (q.get('source', ['auto'])[0] or 'auto').strip().lower()
        archive_ids = set(handler.sensor_ids_from_archive()) if source_mode in ('archive', 'combined', 'auto') else set()

        local_ids = set()
        if source_mode in ('local', 'combined', 'auto'):
            handler.store.poll_new()
            for ev in list(handler.store.events):
                de = ev.get('decode') or {}
                sid = de.get('sensor_id')
                if sid is not None:
                    local_ids.add(str(sid))

        if source_mode == 'archive':
            ids = archive_ids
        elif source_mode == 'local':
            ids = local_ids
        elif source_mode == 'combined':
            ids = local_ids | archive_ids
        else:
            ids = local_ids | archive_ids
            source_mode = 'auto'

        return handler._json({'source_mode': source_mode, 'sensor_ids': sorted(ids)})

    return None
