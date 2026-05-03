import json


def handle_path_defaults_get(handler, parsed):
    if parsed.path != '/api/path/defaults':
        return None
    d = handler._load_path_defaults()
    return handler._json({'ok': True, 'defaults': d, 'source': str(handler.PATH_DEFAULTS_PATH)})


def handle_path_defaults_post(handler, parsed):
    if parsed.path != '/api/path/defaults':
        return None
    try:
        length = int(handler.headers.get('Content-Length', '0'))
        raw = handler.rfile.read(length) if length > 0 else b'{}'
        body = json.loads(raw.decode('utf-8', errors='replace'))
        if not isinstance(body, dict):
            return handler._json({'ok': False, 'error': 'body must be object'}, code=400)
        handler._save_path_defaults(body)
        return handler._json({'ok': True, 'source': str(handler.PATH_DEFAULTS_PATH)})
    except Exception as e:
        return handler._json({'ok': False, 'error': str(e)}, code=400)
