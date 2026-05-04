from urllib.parse import parse_qs
from webui.core_http import ApiError, parse_int_param, parse_enum_param, error_payload


def handle_events_get(handler, parsed):
    if parsed.path == '/api/events':
        try:
            q = parse_qs(parsed.query)
            limit = parse_int_param(q.get('limit', ['100'])[0], name='limit', default=100, min_value=1, max_value=4000)
            handler.store.poll_new()
            events = list(handler.store.events)[-limit:]
            events = handler._with_sensor_mapping(events)
            return handler._json({'events': events, 'count': len(handler.store.events), 'source': str(handler.store.path)})
        except ApiError as e:
            return handler._json(error_payload(e.code, e.message, e.field), code=e.http_code)

    if parsed.path == '/api/sensors':
        try:
            q = parse_qs(parsed.query)
            source_mode = parse_enum_param(q.get('source', ['auto'])[0], name='source', allowed={'auto','local','archive','combined'}, default='auto')
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
        except ApiError as e:
            return handler._json(error_payload(e.code, e.message, e.field), code=e.http_code)

    return None
