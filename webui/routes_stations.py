from urllib.parse import parse_qs
import json


def handle_stations_post(handler, parsed):
    if parsed.path == '/api/stations/update':
        try:
            length = int(handler.headers.get('Content-Length', '0'))
            raw = handler.rfile.read(length) if length > 0 else b'{}'
            body = json.loads(raw.decode('utf-8', errors='replace'))
            idx = int(body.get('index'))
            rows = handler._load_stations(limit=100000)
            if idx < 0 or idx >= len(rows):
                return handler._json({'ok': False, 'error': 'index_out_of_range'}, code=400)
            r = rows[idx]
            key = str(r.get('station_key', '') or r.get('unitid', '') or r.get('name', '')).strip()
            nm = str(body.get('name', '')).strip()
            lat = str(body.get('lat', '')).strip()
            lon = str(body.get('lon', '')).strip()
            elev = str(body.get('elevation', '')).strip()
            enabled = str(body.get('enabled', '')).strip()

            cat = handler.load_meta_catalog('config/meta_catalog.json')
            arr = cat.get('stations', [])
            pos = next((i for i, s in enumerate(arr) if str(s.get('station_key', '')).strip() == key), -1)
            item = arr[pos] if pos >= 0 else {
                'station_key': key,
                'bom_stn': str(r.get('unitid', '')).strip(),
                'name': str(r.get('name', '') or r.get('unitname', '')).strip(),
                'location': str(r.get('location', '') or r.get('name', '') or r.get('unitname', '')).strip(),
                'enabled': True,
                'active': True,
            }
            if nm:
                item['name'] = nm
                item['location'] = nm
            if lat != '':
                item['lat'] = lat
            if lon != '':
                item['lon'] = lon
            if elev != '':
                item['elevation_m'] = elev
            if enabled != '':
                item['enabled'] = (str(enabled).strip() not in ('0', 'false', 'False', 'no'))
            if pos >= 0:
                arr[pos] = item
            else:
                arr.append(item)
            cat['stations'] = arr
            handler.save_meta_catalog(cat, 'config/meta_catalog.json')
            handler._write_stations_master(handler._load_stations(limit=100000))
            return handler._json({'ok': True, 'index': idx, 'station_key': key})
        except Exception as e:
            return handler._json({'ok': False, 'error': str(e)}, code=400)

    if parsed.path == '/api/stations/delete':
        try:
            length = int(handler.headers.get('Content-Length', '0'))
            raw = handler.rfile.read(length) if length > 0 else b'{}'
            body = json.loads(raw.decode('utf-8', errors='replace'))
            idx = int(body.get('index'))
            rows = handler._load_stations(limit=100000)
            if idx < 0 or idx >= len(rows):
                return handler._json({'ok': False, 'error': 'index_out_of_range'}, code=400)
            r = rows[idx]
            key = str(r.get('station_key', '') or r.get('unitid', '') or r.get('name', '')).strip()
            cat = handler.load_meta_catalog('config/meta_catalog.json')
            arr = cat.get('stations', [])
            n = len(arr)
            arr = [s for s in arr if str(s.get('station_key', '')).strip() != key]
            cat['stations'] = arr
            handler.save_meta_catalog(cat, 'config/meta_catalog.json')
            handler._write_stations_master(handler._load_stations(limit=100000))
            return handler._json({'ok': True, 'deleted': n-len(arr), 'station_key': key})
        except Exception as e:
            return handler._json({'ok': False, 'error': str(e)}, code=400)

    if parsed.path == '/api/stations/upload':
        try:
            length = int(handler.headers.get('Content-Length', '0'))
            raw = handler.rfile.read(length) if length > 0 else b'{}'
            body = json.loads(raw.decode('utf-8', errors='replace'))
            txt = str(body.get('csv_text', ''))
            if not txt.strip():
                return handler._json({'ok': False, 'error': 'empty_csv'}, code=400)
            parsed_rows = handler._parse_stations_csv_text(txt, limit=50000)
            if not parsed_rows:
                return handler._json({'ok': False, 'error': 'parse_failed_no_rows', 'hint': 'check delimiter/header includes Latitude/Longitude'}, code=400)
            handler.STATIONS_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
            handler.STATIONS_CSV_PATH.write_text(txt, encoding='utf-8')
            handler._write_stations_master(handler._load_stations(limit=100000))
            return handler._json({'ok': True, 'count': len(parsed_rows), 'source': str(handler.STATIONS_CSV_PATH)})
        except Exception as e:
            return handler._json({'ok': False, 'error': str(e)}, code=400)

    return None


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
