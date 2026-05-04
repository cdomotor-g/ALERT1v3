from urllib.parse import parse_qs
import time
from webui.core_http import ApiError, parse_int_param, parse_enum_param, error_payload


def handle_trends_get(handler, parsed):
    if parsed.path != '/api/trends':
        return None
    try:
        q = parse_qs(parsed.query)
        sensor_id = (q.get('sensor_id', [''])[0] or '').strip()
        win = (q.get('window', ['24h'])[0] or '24h').strip().lower()
        source_mode = parse_enum_param(q.get('source', ['auto'])[0], name='source', allowed={'auto', 'local', 'archive', 'combined'}, default='auto')
        metric = parse_enum_param(q.get('metric', ['raw'])[0], name='metric', allowed={'raw', 'delta', 'rate', 'threshold'}, default='raw')
        threshold = q.get('threshold', [None])[0]
        limit = parse_int_param(q.get('limit', ['2000'])[0], name='limit', default=2000, min_value=100, max_value=10000)
        if win not in {'1h', '3h', '6h', '12h', '24h', '48h', '72h', '7d'}:
            raise ApiError('invalid_param', 'window must be one of 1h,3h,6h,12h,24h,48h,72h,7d', 'window', 400)

        handler.store.poll_new()
        cutoff = time.time() - handler.window_seconds(win)
        local_points = []
        for ev in list(handler.store.events):
            de = ev.get('decode') or {}
            if str(de.get('sensor_id', '')) != sensor_id:
                continue
            ts = ev.get('ts', '')
            dt = handler.parse_ts(ts)
            if not dt or dt.timestamp() < cutoff:
                continue
            v = de.get('data_val')
            if isinstance(v, (int, float)):
                local_points.append({'ts': ts, 'value': float(v)})
        local_points = local_points[-limit:]

        archive_res = {'points': [], 'source': 'archive:none'}
        if source_mode in ('archive', 'combined', 'auto'):
            archive_res = handler.trends_from_archive(sensor_id, win, limit)
        archive_points = archive_res['points']

        if source_mode == 'archive':
            base_points = archive_points
            resolved_source = 'archive'
        elif source_mode == 'local':
            base_points = local_points
            resolved_source = 'local'
        elif source_mode == 'combined':
            base_points = handler.merge_points(local_points, archive_points, limit)
            resolved_source = 'combined'
        else:
            if len(local_points) >= max(20, limit // 10):
                base_points = local_points
                resolved_source = 'local'
            else:
                base_points = handler.merge_points(local_points, archive_points, limit)
                resolved_source = 'auto'

        points = handler.apply_metric(base_points, metric, threshold)
        vals = [p['value'] for p in points]
        stats = {
            'latest': vals[-1] if vals else None,
            'min': min(vals) if vals else None,
            'max': max(vals) if vals else None,
            'avg': round(sum(vals)/len(vals), 3) if vals else None,
            'local_count': len(local_points),
            'archive_count': len(archive_points),
        }
        return handler._json({
            'sensor_id': sensor_id,
            'window': win,
            'source_mode': resolved_source,
            'metric': metric,
            'points': points,
            'stats': stats,
            'source': {'local': str(handler.store.path), 'archive': archive_res.get('source', 'archive:none')}
        })
    except ApiError as e:
        return handler._json(error_payload(e.code, e.message, e.field), code=e.http_code)
