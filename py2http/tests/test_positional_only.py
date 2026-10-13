"""Positional-only parameters (``dict.__getitem__``, ``def f(x, /)``) can be called over
JSON, which supplies arguments by name (i2mint/py2http#13, #14)."""

import io
import json
from wsgiref.util import setup_testing_defaults

import pytest
from i2.errors import InputError

from py2http import mk_app
from py2http.util import call_with_inputs


def test_call_with_inputs_passes_positional_only_by_name():
    assert call_with_inputs(lambda x, /, y: (x, y), kwargs={"y": 2, "x": 1}) == (1, 2)


def test_call_with_inputs_leaves_ordinary_calls_alone():
    assert call_with_inputs(lambda x, y=0: (x, y), (1,), {"y": 2}) == (1, 2)
    assert call_with_inputs(lambda *a, **k: (a, k), (1,), {"z": 2}) == ((1,), {"z": 2})


def test_explicit_positional_args_come_first():
    assert call_with_inputs(lambda x, y, /: (x, y), (1,), {"y": 2}) == (1, 2)


def test_optional_positional_only():
    def f(a, b=5, c=6, /):
        return a, b, c

    assert call_with_inputs(f, kwargs={"a": 1}) == (1, 5, 6)
    assert call_with_inputs(f, kwargs={"a": 1, "c": 9}) == (1, 5, 9)


def test_missing_required_positional_only_is_an_input_error():
    with pytest.raises(InputError, match="'y'"):
        call_with_inputs(lambda x, y, /: None, kwargs={"x": 1})


def test_callable_without_a_signature_gets_kwargs_as_before(monkeypatch):
    import py2http.util

    def no_signature(func):
        raise ValueError("no signature found")

    monkeypatch.setattr(py2http.util, "signature", no_signature)
    assert call_with_inputs(lambda **kw: kw, kwargs={"x": 1}) == {"x": 1}


def test_container_methods_without_a_readable_signature(monkeypatch):
    """Python 3.10 can't read ``dict.__getitem__``'s or ``dict.pop``'s signature."""
    import py2http.util

    def no_signature(func):
        raise ValueError("no signature found")

    monkeypatch.setattr(py2http.util, "signature", no_signature)
    d = {"a": 1, "b": 2}
    assert call_with_inputs(d.__getitem__, kwargs={"key": "a"}) == 1
    assert call_with_inputs([5, 6].__getitem__, kwargs={"index": 1}) == 6
    assert call_with_inputs(d.pop, kwargs={"key": "a"}) == 1
    assert call_with_inputs(d.pop, kwargs={"key": "zz", "default": 0}) == 0
    assert d == {"b": 2}


def _post(app, path, payload):
    body = json.dumps(payload).encode()
    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": path,
        "CONTENT_TYPE": "application/json",
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": io.BytesIO(body),
    }
    setup_testing_defaults(environ)
    statuses = []
    out = b"".join(app(environ, lambda status, headers, *a: statuses.append(status)))
    return statuses[0], json.loads(out)


def test_dict_dunders_over_http():
    store = {"some_key": "some_value"}
    app = mk_app(
        [
            dict(
                endpoint=store,
                name="backend_store",
                attr_names=["__getitem__", "__setitem__"],
                obj_owner=lambda req: "anyone",
            )
        ]
    )
    status, value = _post(
        app, "/backend_store", {"_attr_name": "__getitem__", "key": "some_key"}
    )
    assert status.startswith("200") and value == "some_value"
    payload = {"_attr_name": "__setitem__", "key": "k", "value": 1}
    assert _post(app, "/backend_store", payload)[0].startswith("200")
    assert store["k"] == 1
    status, _ = _post(app, "/backend_store", {"_attr_name": "__getitem__"})
    assert status.startswith("400")  # missing 'key': a client error


def test_plain_function_with_positional_only_over_http():
    def add(x, y, /):
        return x + y

    app = mk_app([add])
    assert _post(app, "/add", {"x": 1, "y": 2}) == ("200 OK", 3)


def test_optional_positional_only_stays_a_keyword_when_there_is_var_keyword():
    # Counter.update(iterable=None, /, **kwds): ``iterable`` is a keyword here
    from collections import Counter, UserDict

    assert call_with_inputs(lambda a=0, /, **kw: (a, kw), kwargs={"a": 1}) == (
        0,
        {"a": 1},
    )
    c = Counter()
    call_with_inputs(c.update, kwargs={"iterable": 3})
    assert c == Counter(iterable=3)
    d = UserDict()
    call_with_inputs(d.update, kwargs={"other": 1})
    assert dict(d) == {"other": 1}


def test_required_positional_only_is_bound_even_with_var_keyword():
    assert call_with_inputs(lambda a, /, **kw: (a, kw), kwargs={"a": 1, "b": 2}) == (
        1,
        {"b": 2},
    )


def test_class_endpoint_with_positional_only_constructor():
    from py2http.service import _get_func_to_dispatch_handler, shared_objects

    class Box:
        def __init__(self, content, /):
            self.content = content

        def get(self):
            return self.content

    func = _get_func_to_dispatch_handler(
        dict(endpoint=Box, name="box", attr_names=["get"], obj_owner=shared_objects)
    )
    obj_id = func(content=7)
    assert func(_obj_id=obj_id, _attr_name="get") == 7
