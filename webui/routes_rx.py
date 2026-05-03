import json


def handle_rx_get(handler, parsed):
    if parsed.path == '/api/rx_agg':
        if handler.RX_AGG_JSON_PATH.exists():
            try:
                d = json.loads(handler.RX_AGG_JSON_PATH.read_text(encoding='utf-8', errors='replace'))
                d['source'] = str(handler.RX_AGG_JSON_PATH)
                return handler._json(d)
            except Exception as e:
                return handler._json({'error': f'parse_failed: {e}', 'source': str(handler.RX_AGG_JSON_PATH)}, code=500)
        return handler._json({'error': 'not_ready', 'source': str(handler.RX_AGG_JSON_PATH)}, code=404)

    return None
