def handle_meta_get(handler, parsed):
    if parsed.path in ['/api/meta/catalog', '/api/meta/export']:
        cat = handler.load_meta_catalog()
        cat['source'] = 'config/meta_catalog.json'
        return handler._json(cat)

    if parsed.path == '/api/deployment_role':
        d = handler.load_deployment_role()
        d['source'] = 'config/deployment_role.json'
        return handler._json(d)

    return None
