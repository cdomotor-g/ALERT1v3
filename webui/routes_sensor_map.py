def handle_sensor_map_get(handler, parsed):
    if parsed.path != '/api/sensor_map/status':
        return None
    sm = handler._load_sensor_map(limit=100000)
    return handler._json({'ok': True, 'path': str(handler.SENSOR_MAP_CSV_PATH), 'exists': handler.SENSOR_MAP_CSV_PATH.exists(), 'mapped_alert1_ids': len(sm)})
