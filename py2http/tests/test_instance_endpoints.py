"""Instance endpoints (one object every client shares) need an owner hook and are
bounded in size (#30)."""

import io
import json
from wsgiref.util import setup_testing_defaults

import pytest
from i2.errors import AuthorizationError, InputError

from py2http import mk_app
from py2http.service import (
    _get_func_to_dispatch_handler,
    current_request,
    shared_objects,
)


class Store(dict):
    """A mapping clients may write to."""

    def write(self, key, value):
        self[key] = value
        return len(self)

    def read(self, key):
        return self[key]

    def remove(self, key):
        del self[key]

    def write_then_fail(self, key, value):
        self[key] = value
        raise ValueError("invalid")


def _instance(endpoint=None, **extras):
    extras.setdefault("obj_owner", lambda req: req)  # the "request" is the owner here
    extras.setdefault("attr_names", "*")
    endpoint = Store() if endpoint is None else endpoint
    return _get_func_to_dispatch_handler(dict(endpoint=endpoint, name="store", **extras))


def _as(owner, func, **kwargs):
    token = current_request.set(owner)
    try:
        return func(**kwargs)
    finally:
        current_request.reset(token)


def test_instance_endpoint_without_owner_is_refused_at_build():
    with pytest.raises(ValueError, match="obj_owner"):
        _get_func_to_dispatch_handler(dict(endpoint=Store(), name="s", attr_names="*"))


def test_bad_owner_hook_is_refused_at_build():
    with pytest.raises(TypeError, match="obj_owner"):
        _instance(obj_owner="ann")


def test_module_endpoint_needs_no_owner():
    import os.path as module

    func = _get_func_to_dispatch_handler(
        dict(endpoint=module, name="m", attr_names=["basename"])
    )
    assert func(_attr_name="basename", p="a/b") == "b"


@pytest.mark.parametrize("who", [None, ""])
def test_unidentified_request_is_refused(who):
    store = Store()
    func = _instance(store)
    with pytest.raises(AuthorizationError):
        _as(who, func, _attr_name="write", key="k", value=1)
    assert store == {}


def test_identified_requests_share_the_object():
    func = _instance()
    assert _as("ann", func, _attr_name="write", key="k", value=1) == 1
    assert _as("bob", func, _attr_name="read", key="k") == 1


def test_shared_objects_lets_anyone_in():
    func = _instance(obj_owner=shared_objects)
    assert _as(None, func, _attr_name="write", key="k", value=1) == 1


def test_object_already_too_big_is_refused_at_build():
    with pytest.raises(ValueError, match="max_obj_size"):
        _instance(Store(big="y" * 20_000), max_obj_size=10_000)
    _instance(Store(big="y" * 20_000), max_obj_size=None)  # check disabled


def test_growing_past_the_limit_refuses_until_back_under():
    store = Store()
    func = _instance(store, max_obj_size=10_000)
    _as("ann", func, _attr_name="write", key="a", value="small")
    with pytest.raises(InputError, match="size limit"):
        _as("ann", func, _attr_name="write", key="big", value="y" * 20_000)
    assert "big" in store  # the object is kept, not dropped: it is the endpoint
    with pytest.raises(InputError, match="size limit"):  # even a read, the object is full
        _as("bob", func, _attr_name="read", key="a")
    del store["big"]  # shrunk outside the service
    assert _as("bob", func, _attr_name="read", key="a") == "small"


def test_a_call_that_grows_the_object_then_raises_is_still_measured():
    store = Store()
    func = _instance(store, max_obj_size=10_000)
    with pytest.raises(InputError, match="size limit"):
        _as("ann", func, _attr_name="write_then_fail", key="big", value="y" * 20_000)
    with pytest.raises(InputError, match="size limit"):
        _as("ann", func, _attr_name="write", key="more", value="y" * 20_000)
    assert "more" not in store  # refused before running


def test_custom_sizeof():
    func = _instance(max_obj_size=2, obj_sizeof=lambda obj, limit: len(obj))
    _as("ann", func, _attr_name="write", key="a", value="y" * 20_000)
    _as("ann", func, _attr_name="write", key="b", value=1)
    with pytest.raises(InputError, match="size limit"):
        _as("ann", func, _attr_name="write", key="c", value=1)


def _post(app, path, payload, user):
    body = json.dumps(payload).encode()
    environ = {
        "REQUEST_METHOD": "POST",
        "PATH_INFO": path,
        "CONTENT_TYPE": "application/json",
        "CONTENT_LENGTH": str(len(body)),
        "HTTP_X_USER": user,
        "wsgi.input": io.BytesIO(body),
    }
    setup_testing_defaults(environ)
    statuses = []
    out = b"".join(app(environ, lambda status, headers, *a: statuses.append(status)))
    return statuses[0], json.loads(out)


def test_http_statuses():
    store = Store()
    app = mk_app(
        [
            dict(
                endpoint=store,
                name="store",
                attr_names=["write"],
                obj_owner=lambda req: req.headers.get("X-User"),
                max_obj_size=10_000,
            )
        ]
    )
    payload = {"_attr_name": "write", "key": "k", "value": 1}
    status, n = _post(app, "/store", payload, "ann")
    assert status.startswith("200") and n == 1
    status, _ = _post(app, "/store", payload, "")
    assert status.startswith("401")
    payload = {"_attr_name": "write", "key": "big", "value": "y" * 20_000}
    status, _ = _post(app, "/store", payload, "ann")
    assert status.startswith("400")


def test_shrinkers_run_while_over_the_limit():
    store = Store()
    func = _instance(
        store,
        max_obj_size=10_000,
        attr_names=["write", "read", "remove"],
        obj_shrinkers=["remove"],
    )
    for key in ("a", "b"):
        with pytest.raises(InputError) if key == "b" else _no_error():
            _as("ann", func, _attr_name="write", key=key, value="y" * 6_000)
    with pytest.raises(InputError, match="except remove"):
        _as("ann", func, _attr_name="read", key="a")
    assert _as("ann", func, _attr_name="remove", key="b") is None
    assert _as("ann", func, _attr_name="read", key="a") == "y" * 6_000


def _no_error():
    from contextlib import nullcontext

    return nullcontext()


def test_state_behind_methods_partials_and_closures_is_measured():
    from functools import partial

    from py2http.service import bounded_deep_sizeof

    big = [str(i) * 1000 for i in range(100)]  # distinct strings, not one constant

    class Holder:
        pass

    def closure():
        return big

    for held in (big.append, partial(print, big), closure):
        holder = Holder()
        holder.held = held
        assert bounded_deep_sizeof(holder) > 100_000, held
