from datetime import datetime
from webui.core_http import ApiError, read_json_body, error_payload


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
        body = read_json_body(handler, max_bytes=2_000_000)
        fn = handler.os_path_basename(str(body.get('filename', 'upload.txt')).strip() or 'upload.txt')
        ext = ('.' + fn.lower().split('.')[-1]) if '.' in fn else ''
        allowed_ext = {'.csv', '.txt', '.json'}
        if ext not in allowed_ext:
            raise ApiError('invalid_extension', f'extension {ext or "(none)"} not allowed', 'filename', 400)
        content = str(body.get('content', ''))
        if len(content.encode('utf-8', errors='replace')) > 1_500_000:
            raise ApiError('payload_too_large', 'content exceeds 1.5MB', 'content', 413)

        handler.FILE_DROP_DIR.mkdir(parents=True, exist_ok=True)
        outp = handler.FILE_DROP_DIR / fn
        tmp = outp.with_suffix(outp.suffix + '.tmp')
        tmp.write_text(content, encoding='utf-8', errors='replace')
        tmp.replace(outp)

        ftype = 'generic'
        mapped = 0
        low = fn.lower()
        confirm_promote = bool(body.get('confirm_promote', False))
        if confirm_promote and low.endswith('.csv') and handler._looks_like_sensor_map_csv(content):
            backup = handler.SENSOR_MAP_CSV_PATH.with_suffix('.csv.bak')
            if handler.SENSOR_MAP_CSV_PATH.exists():
                handler.SENSOR_MAP_CSV_PATH.replace(backup)
            handler.SENSOR_MAP_CSV_PATH.parent.mkdir(parents=True, exist_ok=True)
            sm_tmp = handler.SENSOR_MAP_CSV_PATH.with_suffix('.csv.tmp')
            sm_tmp.write_text(content, encoding='utf-8', errors='replace')
            sm_tmp.replace(handler.SENSOR_MAP_CSV_PATH)
            ftype = 'sensor_map'
            mapped = len(handler._load_sensor_map())
            handler._write_stations_master(handler._load_stations(limit=100000))
        return handler._json({'ok': True, 'path': str(outp), 'type': ftype, 'mapped_alert1_ids': mapped, 'promoted': bool(ftype == 'sensor_map')})
    except ApiError as e:
        return handler._json(error_payload(e.code, e.message, e.field), code=e.http_code)
    except Exception as e:
        return handler._json({'ok': False, 'error': str(e)}, code=400)
