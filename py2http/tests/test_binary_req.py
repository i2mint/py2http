"""Binary (octet-stream) request bodies are never unpickled unless explicitly asked."""

import io
import json
import pickle

import pytest

from py2http.constants import BINARY_CONTENT_TYPE
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


class _FakeRequest:
    def __init__(self, body: bytes, *, content_type=BINARY_CONTENT_TYPE):
        self.method = "POST"
        self.content_type = content_type
        self.body = io.BytesIO(body)


def add(x: int, y: int = 1):
    return x + y


def test_binary_req_requires_explicit_loads():
    with pytest.raises(TypeError, match="explicit loads"):
        handle_binary_req(add)
    with pytest.raises(TypeError, match="callable"):
        handle_binary_req(add, loads="pickle")


def test_binary_body_not_unpickled_by_default():
    _calls.clear()
    payload = pickle.dumps(_RecordsWhenUnpickled())
    with pytest.raises(TypeError):
        _get_inputs_from_request(_FakeRequest(payload), BINARY_CONTENT_TYPE)
    assert _calls == []


def test_binary_req_with_safe_loads():
    mapper = handle_binary_req(add, loads=json.loads)
    assert mapper(_FakeRequest(json.dumps({"x": 2, "y": 3}).encode())) == 5


def test_binary_req_rejects_non_mapping():
    mapper = handle_binary_req(add, loads=json.loads)
    with pytest.raises(TypeError, match="not a mapping"):
        mapper(_FakeRequest(b"[1, 2]"))


def test_binary_req_explicit_unsafe_opt_in_still_works():
    mapper = handle_binary_req(add, loads=unsafe_pickle_loads)
    assert mapper(_FakeRequest(pickle.dumps({"x": 2}))) == 3
