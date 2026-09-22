"""Binary (octet-stream) request bodies are never unpickled unless explicitly asked."""

import io
import json
import pickle
from wsgiref.util import setup_testing_defaults

import pytest

from py2http import mk_app
from py2http.constants import BINARY_CONTENT_TYPE, JSON_CONTENT_TYPE
from py2http.decorators import (
    _get_inputs_from_request,
    handle_binary_req,
    unsafe_pickle_loads,
)

_calls = []


def _record(*args):
    _calls.append(args)
    return {}


class _RecordsWhenUnpickled:
    """Unpickling this calls ``_record``: a harmless stand-in for side effects."""

    def __reduce__(self):
        return (_record, ("unpickled",))


@pytest.fixture
def calls():
    _calls.clear()
    yield _calls
    _calls.clear()


class _FakeRequest:
    def __init__(self, body: bytes, *, content_type=BINARY_CONTENT_TYPE):
        self.method = "POST"
        self.content_type = content_type
        self.body = io.BytesIO(body)


def add(x: int, y: int = 1):
    return x + y


def _post(app, path, body: bytes, content_type: str):
    """Call a WSGI app directly; return (status, body)."""
    environ = {}
    setup_testing_defaults(environ)
    environ.update(
        REQUEST_METHOD="POST",
        PATH_INFO=path,
        CONTENT_TYPE=content_type,
        CONTENT_LENGTH=str(len(body)),
    )
    environ["wsgi.input"] = io.BytesIO(body)
    statuses = []
    out = b"".join(app(environ, lambda status, headers, *a: statuses.append(status)))
    return statuses[0], out


def test_binary_req_requires_explicit_loads():
    with pytest.raises(TypeError, match="explicit loads"):
        handle_binary_req(add)
    with pytest.raises(TypeError, match="callable"):
        handle_binary_req(add, loads="pickle")


def test_bare_pickle_loads_warns():
    with pytest.warns(UserWarning, match="unsafe_pickle_loads"):
        handle_binary_req(add, loads=pickle.loads)


def test_binary_body_not_unpickled_by_default(calls):
    payload = pickle.dumps(_RecordsWhenUnpickled())
    with pytest.raises(TypeError, match="No decoder"):
        _get_inputs_from_request(_FakeRequest(payload), BINARY_CONTENT_TYPE)
    assert calls == []


def test_binary_req_with_safe_loads(calls):
    mapper = handle_binary_req(add, loads=json.loads)
    assert mapper(_FakeRequest(json.dumps({"x": 2, "y": 3}).encode())) == 5
    with pytest.raises(ValueError):
        mapper(_FakeRequest(pickle.dumps(_RecordsWhenUnpickled())))
    assert calls == []


def test_binary_req_rejects_non_mapping():
    mapper = handle_binary_req(add, loads=json.loads)
    with pytest.raises(TypeError, match="not a mapping"):
        mapper(_FakeRequest(b"[1, 2]"))


def test_binary_req_explicit_unsafe_opt_in_still_works():
    mapper = handle_binary_req(add, loads=unsafe_pickle_loads)
    assert mapper(_FakeRequest(pickle.dumps({"x": 2}))) == 3


def test_default_service_does_not_unpickle_octet_stream_bodies(calls):
    app = mk_app([add])
    status, _ = _post(
        app, "/add", pickle.dumps(_RecordsWhenUnpickled()), BINARY_CONTENT_TYPE
    )
    assert not status.startswith("2")
    assert calls == []
    # the normal JSON path still works
    status, body = _post(app, "/add", json.dumps({"x": 2}).encode(), JSON_CONTENT_TYPE)
    assert status.startswith("200") and json.loads(body) == 3
