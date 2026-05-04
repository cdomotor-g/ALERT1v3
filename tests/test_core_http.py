import io
import pytest

from webui.core_http import ApiError, parse_int_param, parse_enum_param, read_json_body


def test_parse_int_param_ok_and_range():
    assert parse_int_param('10', name='limit', min_value=1, max_value=20) == 10
    with pytest.raises(ApiError):
        parse_int_param('0', name='limit', min_value=1, max_value=20)


def test_parse_enum_param():
    assert parse_enum_param('AUTO', name='source', allowed={'auto', 'local'}, default='auto') == 'auto'
    with pytest.raises(ApiError):
        parse_enum_param('bad', name='source', allowed={'auto', 'local'}, default='auto')


class DummyHandler:
    def __init__(self, raw: bytes):
        self.headers = {'Content-Length': str(len(raw))}
        self.rfile = io.BytesIO(raw)


def test_read_json_body_ok():
    h = DummyHandler(b'{"a":1}')
    body = read_json_body(h, max_bytes=100)
    assert body['a'] == 1


def test_read_json_body_oversize():
    raw = b'{' + b'a' * 200 + b'}'
    h = DummyHandler(raw)
    with pytest.raises(ApiError) as e:
        read_json_body(h, max_bytes=10)
    assert e.value.code == 'payload_too_large'
