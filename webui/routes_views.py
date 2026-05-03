import json
import time


def handle_views_get(handler, parsed):
    if parsed.path != '/api/views':
        return None
    return handler._json({'views': handler.load_saved_views()})


def handle_views_post(handler, parsed):
    if parsed.path != '/api/views':
        return None
    try:
        length = int(handler.headers.get('Content-Length', '0'))
        raw = handler.rfile.read(length) if length > 0 else b'{}'
        body = json.loads(raw.decode('utf-8'))
        if not isinstance(body, dict):
            raise ValueError('body must be object')
        views = handler.load_saved_views()
        view = {
            'id': int(time.time() * 1000),
            'name': str(body.get('name', 'view')).strip() or 'view',
            'sensor_id': str(body.get('sensor_id', '')).strip(),
            'window': str(body.get('window', '24h')),
            'source': str(body.get('source', 'local')),
            'metric': str(body.get('metric', 'raw')),
            'threshold': body.get('threshold', None),
        }
        views.append(view)
        handler.save_saved_views(views)
        return handler._json({'ok': True, 'view': view})
    except Exception as e:
        return handler._json({'ok': False, 'error': str(e)}, code=400)
