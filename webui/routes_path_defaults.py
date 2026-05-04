from webui.core_http import ApiError, read_json_body, error_payload


def handle_path_defaults_get(handler, parsed):
    if parsed.path != '/api/path/defaults':
        return None
    d = handler._load_path_defaults()
    return handler._json({'ok': True, 'defaults': d, 'source': str(handler.PATH_DEFAULTS_PATH)})


def handle_path_defaults_post(handler, parsed):
    if parsed.path != '/api/path/defaults':
        return None
    ra = handler.client_address[0] if handler.client_address else ''
    if not handler.admin_authorized(handler.headers, ra):
        handler.audit_admin_action(parsed.path, ra, False, {'error': 'unauthorized'})
        return handler._json({'ok': False, 'error': 'unauthorized'}, code=403)
    try:
        body = read_json_body(handler, max_bytes=65536)
        allowed = {'window', 'source', 'metric', 'threshold', 'sensor_id', 'limit'}
        extra = [k for k in body.keys() if k not in allowed]
        if extra:
            raise ApiError('invalid_param', f'unknown keys: {", ".join(extra)}', 'body', 400)
        handler._save_path_defaults(body)
        handler.audit_admin_action(parsed.path, ra, True, {'keys': sorted(list(body.keys()))})
        return handler._json({'ok': True, 'source': str(handler.PATH_DEFAULTS_PATH)})
    except ApiError as e:
        handler.audit_admin_action(parsed.path, ra, False, {'error': e.message, 'code': e.code})
        return handler._json(error_payload(e.code, e.message, e.field), code=e.http_code)
    except Exception as e:
        handler.audit_admin_action(parsed.path, ra, False, {'error': str(e)})
        return handler._json({'ok': False, 'error': str(e)}, code=400)
