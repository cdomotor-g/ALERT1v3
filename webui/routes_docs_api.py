def handle_docs_api_get(handler, parsed):
    if parsed.path == '/api/flowgraph_doc':
        return handler._json(handler._flowgraph_doc())
    return None
