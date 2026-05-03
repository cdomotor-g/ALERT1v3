from urllib.parse import parse_qs


def handle_stations_get(handler, parsed):
    if parsed.path != '/api/stations/catalog':
        return None
    q = parse_qs(parsed.query)
    qtxt = str((q.get('q', [''])[0] or '')).strip().lower()
    limit = int((q.get('limit', ['20'])[0] or '20'))
    limit = max(1, min(limit, 200))
    rows = handler._load_stations(limit=100000)
    out = []
    for i, r in enumerate(rows):
        unitid = str(r.get('unitid', r.get('site_id_bom', ''))).strip()
        unitname = str(r.get('unitname', r.get('name', ''))).strip()
        loc = str(r.get('location', unitname)).strip()
        arro = str(r.get('arro_site_id', '')).strip()
        blob = f"{unitid} {unitname} {loc} {arro}".lower()
        if qtxt and qtxt not in blob:
            continue
        out.append({
            'index': i,
            'unitid': unitid,
            'unitname': unitname,
            'location': loc,
            'arro_site_id': arro,
            'lat': r.get('latitude', ''),
            'lon': r.get('longitude', ''),
            'enabled': r.get('enabled', ''),
        })
        if len(out) >= limit:
            break
    return handler._json({'items': out, 'count': len(out), 'q': qtxt})
