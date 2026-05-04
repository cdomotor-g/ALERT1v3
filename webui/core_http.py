import json


class ApiError(Exception):
    def __init__(self, code: str, message: str, field: str | None = None, http_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field
        self.http_code = http_code


def error_payload(code: str, message: str, field: str | None = None):
    e = {'code': code, 'message': message}
    if field:
        e['field'] = field
    return {'ok': False, 'error': e}


def parse_int_param(raw, *, name: str, default: int | None = None, min_value: int | None = None, max_value: int | None = None):
    if raw is None or raw == '':
        if default is None:
            raise ApiError('missing_param', f'missing {name}', name, 400)
        v = int(default)
    else:
        try:
            v = int(raw)
        except Exception:
            raise ApiError('invalid_param', f'{name} must be integer', name, 400)
    if min_value is not None and v < min_value:
        raise ApiError('out_of_range', f'{name} must be >= {min_value}', name, 400)
    if max_value is not None and v > max_value:
        raise ApiError('out_of_range', f'{name} must be <= {max_value}', name, 400)
    return v


def parse_enum_param(raw, *, name: str, allowed: set[str], default: str | None = None):
    v = (str(raw).strip().lower() if raw is not None else '')
    if not v:
        if default is None:
            raise ApiError('missing_param', f'missing {name}', name, 400)
        v = default
    if v not in allowed:
        raise ApiError('invalid_param', f'{name} must be one of: {", ".join(sorted(allowed))}', name, 400)
    return v


def read_json_body(handler, *, max_bytes: int = 262144):
    try:
        length = int(handler.headers.get('Content-Length', '0') or '0')
    except Exception:
        raise ApiError('invalid_content_length', 'invalid Content-Length', 'Content-Length', 400)
    if length < 0:
        raise ApiError('invalid_content_length', 'invalid Content-Length', 'Content-Length', 400)
    if length > max_bytes:
        raise ApiError('payload_too_large', f'payload exceeds {max_bytes} bytes', None, 413)
    raw = handler.rfile.read(length) if length > 0 else b'{}'
    try:
        body = json.loads(raw.decode('utf-8', errors='replace'))
    except Exception:
        raise ApiError('invalid_json', 'request body must be valid JSON', None, 400)
    if not isinstance(body, dict):
        raise ApiError('invalid_json_type', 'body must be object', None, 400)
    return body
