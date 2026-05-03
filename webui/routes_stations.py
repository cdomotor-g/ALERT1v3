from urllib.parse import parse_qs


def handle_stations_get(handler, parsed):
    if parsed.path == '/api/stations':
        q = parse_qs(parsed.query)
        limit = int((q.get('limit', ['5000'])[0] or '5000'))
        rows = handler._load_stations(limit=limit)
        return handler._json({'rows': rows, 'count': len(rows)})

    if parsed.path == '/api/stations/rows':
        q = parse_qs(parsed.query)
        limit = int((q.get('limit', ['5000'])[0] or '5000'))
        limit = max(1, min(limit, 200000))
        rows = handler._load_stations(limit=limit)
        out = []
        for i, r in enumerate(rows):
            out.append({
                'index': i,
                'unitid': str(r.get('unitid', r.get('site_id_bom', ''))).strip(),
                'name': str(r.get('unitname', r.get('name', ''))).strip(),
                'location': str(r.get('location', r.get('unitname', r.get('name', '')))).strip(),
                'lat': str(r.get('latitude', '')).strip(),
                'lon': str(r.get('longitude', '')).strip(),
                'elevation': str(r.get('elevation', '')).strip(),
                'enabled': str(r.get('enabled', '1')).strip(),
                'icon': str(r.get('icon', '')).strip(),
                'style': str(r.get('style', '')).strip(),
                'locked': str(r.get('locked', '')).strip(),
                'sensor_types': str(r.get('sensor_types', '')).strip(),
                'sensor_ids': str(r.get('sensor_ids', '')).strip(),
                'device_ids': str(r.get('device_ids', '')).strip(),
                'kml_name': str(r.get('kml_name', '')).strip(),
                'arro_site_id': str(r.get('arro_site_id', '')).strip(),
                'station_key': str(r.get('station_key', '')).strip(),
            })
        return handler._json({'rows': out, 'count': len(out)})
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
