from urllib.parse import parse_qs


def handle_forensics_get(handler, parsed):
    if parsed.path == '/api/forensics_bundle':
        q = parse_qs(parsed.query)
        limit = int(q.get('limit', ['300'])[0])
        return handler._json(handler._forensics_bundle(limit=limit))

    if parsed.path == '/api/pair_pattern_stats':
        q = parse_qs(parsed.query)
        limit = int(q.get('limit', ['2000'])[0])
        return handler._json(handler._pair_pattern_stats(limit=limit))

    return None
