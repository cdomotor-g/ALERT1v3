def handle_status_get(handler, parsed):
    if parsed.path == '/api/storage_status':
        return handler._json(handler.storage_status())

    if parsed.path == '/api/receiver_status':
        handler.store.poll_new()
        return handler._json(handler.receiver_status())

    if parsed.path == '/api/host_metrics':
        if not handler.host_metrics_store:
            return handler._json({'event': None, 'enabled': False})
        handler.host_metrics_store.poll_new()
        ev = list(handler.host_metrics_store.events)[-1] if handler.host_metrics_store.events else None
        return handler._json({'event': ev, 'enabled': True})

    return None
