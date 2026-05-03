import json
from datetime import datetime


def handle_filedrop_get(handler, parsed):
    if parsed.path != '/api/file_drop/list':
        return None
    q = handler.parse_qs(parsed.query)
    try:
        limit = int((q.get('limit', ['20'])[0] or '20'))
    except Exception:
        limit = 20
    limit = max(1, min(limit, 200))
    handler.FILE_DROP_DIR.mkdir(parents=True, exist_ok=True)
    files = []
    for p in sorted(handler.FILE_DROP_DIR.glob('*'), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
        try:
            st = p.stat()
            ftype = 'generic'
            try:
                txt = p.read_text(encoding='utf-8', errors='replace')[:8000].lower()
                if p.suffix.lower() == '.csv' and ('sensor id' in txt and 'site id' in txt and 'device_id' in txt):
                    ftype = 'sensor_map_candidate'
            except Exception:
                pass
            files.append({'name': p.name, 'size': st.st_size, 'mtime': datetime.utcfromtimestamp(st.st_mtime).isoformat()+'Z', 'type': ftype})
        except Exception:
            continue
    return handler._json({'count': len(files), 'files': files, 'dir': str(handler.FILE_DROP_DIR), 'sensor_map_path': str(handler.SENSOR_MAP_CSV_PATH), 'sensor_map_exists': handler.SENSOR_MAP_CSV_PATH.exists()})


def handle_filedrop_post(handler, parsed):
    if parsed.path != '/api/file_drop/upload':
        return None
    try:
        length = int(handler.headers.get('Content-Length', '0'))
        raw = handler.rfile.read(length) if length > 0 else b'{}'
        body = json.loads(raw.decode('utf-8', errors='replace'))
        fn = handler.os_path_basename(str(body.get('filename', 'upload.txt')).strip() or 'upload.txt')
        content = str(body.get('content', ''))
        handler.FILE_DROP_DIR.mkdir(parents=True, exist_ok=True)
        outp = handler.FILE_DROP_DIR / fn
        outp.write_text(content, encoding='utf-8', errors='replace')
        ftype = 'generic'
        mapped = 0
        low = fn.lower()
        if low.endswith('.csv') and handler._looks_like_sensor_map_csv(content):
            handler.SENSOR_MAP_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
            handler.SENSOR_MAP_CSV_PATH.write_text(content, encoding='utf-8', errors='replace')
            ftype = 'sensor_map'
            mapped = len(handler._load_sensor_map())
            handler._write_stations_master(handler._load_stations(limit=100000))
        return handler._json({'ok': True, 'path': str(outp), 'type': ftype, 'mapped_alert1_ids': mapped})
    except Exception as e:
        return handler._json({'ok': False, 'error': str(e)}, code=400)
