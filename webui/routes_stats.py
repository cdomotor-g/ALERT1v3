from urllib.parse import parse_qs


def handle_stats_get(handler, parsed):
    if parsed.path == '/api/error_stats':
        q = parse_qs(parsed.query)
        limit = int(q.get('limit', ['50000'])[0])
        mode = str(q.get('mode', ['occurrence'])[0])
        return handler._json(handler._error_stats(limit=limit, mode=mode))

    if parsed.path == '/api/anomaly_stats':
        q = parse_qs(parsed.query)
        limit = int(q.get('limit', ['4000'])[0])
        return handler._json(handler._anomaly_stats(limit=limit))

    return None
