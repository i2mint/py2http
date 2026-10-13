"""Object endpoints: ``obj_readers`` skip measuring, lazy results are measured when
they finish, module endpoints take an optional owner gate, and every 401 names a
challenge (#32)."""

import asyncio

import pytest
from aiohttp import web
from i2.errors import AuthorizationError, InputError

from py2http import mk_app
from py2http.bottle_plugins import ApiKeyAuthPlugin, JWTPlugin
from py2http.default_configs import aiohttp_error_handler
from py2http.service import _get_func_to_dispatch_handler
from py2http.tests.utils_for_testing import as_owner, call_wsgi


class Store(dict):
    def write(self, key, value):
        self[key] = value

    def read(self, key):
        return self[key]

    def fill_lazily(self, n):
        for i in range(n):
            self[i] = "y" * 1_000
            yield i

    async def fill_async(self, n):
        for i in range(n):
            self[i] = "y" * 1_000
        return n


class _Counting:
    def __init__(self):
        self.calls = 0

    def __call__(self, obj, limit):
        self.calls += 1
        return len(obj)


def _instance(store, **extras):
    extras.setdefault("obj_owner", lambda req: req)
    return _get_func_to_dispatch_handler(
        dict(endpoint=store, name="store", attr_names="*", **extras)
    )


def test_obj_readers_are_not_measured():
    sizeof = _Counting()
    func = _instance(Store(), max_obj_size=10, obj_sizeof=sizeof, obj_readers={"read"})
    built = sizeof.calls
    as_owner("ann", func, _attr_name="write", key="a", value=1)
    assert sizeof.calls == built + 1
    for _ in range(5):
        assert as_owner("ann", func, _attr_name="read", key="a") == 1
    assert sizeof.calls == built + 1


def test_class_endpoint_readers_are_not_measured():
    sizeof = _Counting()
    func = _get_func_to_dispatch_handler(
        dict(
            endpoint=Store,
            name="bag",
            attr_names="*",
            obj_owner=lambda req: req,
            obj_sizeof=sizeof,
            obj_readers=["read"],
        )
    )
    obj_id = as_owner("ann", func)
    as_owner("ann", func, _obj_id=obj_id, _attr_name="write", key="a", value=1)
    measured = sizeof.calls
    as_owner("ann", func, _obj_id=obj_id, _attr_name="read", key="a")
    assert sizeof.calls == measured


@pytest.mark.parametrize(
    "readers, error", [("read", TypeError), (["nope"], ValueError)]
)
def test_obj_readers_are_validated(readers, error):
    with pytest.raises(error, match="obj_readers"):
        _instance(Store(), obj_readers=readers)


def test_a_generator_is_measured_when_it_finishes():
    store = Store()
    func = _instance(store, max_obj_size=5, obj_sizeof=lambda obj, limit: len(obj))
    gen = as_owner("ann", func, _attr_name="fill_lazily", n=10)
    assert store == {}  # nothing ran yet: measuring now would see nothing
    with pytest.raises(InputError, match="size limit"):
        list(gen)
    with pytest.raises(InputError, match="size limit"):  # and the next call is refused
        as_owner("ann", func, _attr_name="write", key="x", value=1)


def test_a_coroutine_is_measured_when_it_finishes():
    store = Store()
    func = _instance(store, max_obj_size=5, obj_sizeof=lambda obj, limit: len(obj))
    coro = as_owner("ann", func, _attr_name="fill_async", n=10)
    with pytest.raises(InputError, match="size limit"):
        asyncio.run(coro)


def test_class_endpoint_drops_an_object_a_generator_grew():
    func = _get_func_to_dispatch_handler(
        dict(
            endpoint=Store,
            name="bag",
            attr_names="*",
            obj_owner=lambda req: req,
            max_obj_size=5,
            obj_sizeof=lambda obj, limit: len(obj),
        )
    )
    obj_id = as_owner("ann", func)
    gen = as_owner("ann", func, _obj_id=obj_id, _attr_name="fill_lazily", n=10)
    with pytest.raises(InputError, match="dropped"):
        list(gen)
    with pytest.raises(InputError, match="No object"):
        as_owner("ann", func, _obj_id=obj_id, _attr_name="read", key=0)


def test_module_endpoint_takes_an_optional_owner_gate():
    import os.path as module

    gated = _get_func_to_dispatch_handler(
        dict(endpoint=module, name="m", attr_names=["basename"], obj_owner=lambda r: r)
    )
    assert as_owner("ann", gated, _attr_name="basename", p="/a/b") == "b"
    with pytest.raises(AuthorizationError):
        as_owner(None, gated, _attr_name="basename", p="/a/b")


# ---------------------------------------------------------------------------
# 401 responses name a challenge (RFC 7235)
# ---------------------------------------------------------------------------


def _unidentified():
    raise AuthorizationError("who are you")


def test_a_raised_authorization_error_names_a_challenge(monkeypatch, capsys):
    app = mk_app([_unidentified])
    status, _, headers = call_wsgi(app, "/_unidentified", {}, with_headers=True)
    assert status.startswith("401") and headers["www-authenticate"] == "Bearer"
    monkeypatch.setenv("PY2HTTP_WWW_AUTHENTICATE", 'Basic realm="api"')
    _, _, headers = call_wsgi(app, "/_unidentified", {}, with_headers=True)
    assert headers["www-authenticate"] == 'Basic realm="api"'


def test_aiohttp_401_names_a_challenge():
    with pytest.raises(web.HTTPUnauthorized) as caught:
        aiohttp_error_handler(AuthorizationError("who"))
    assert caught.value.headers["WWW-Authenticate"] == "Bearer"
    with pytest.raises(web.HTTPBadRequest) as caught:
        aiohttp_error_handler(InputError("bad"))
    assert "WWW-Authenticate" not in caught.value.headers


def whoami():
    return "me"


@pytest.mark.parametrize(
    "plugin, challenge",
    [(JWTPlugin("s3cret-for-tests-only-0123456789abcdef"), "Bearer"),
     (ApiKeyAuthPlugin("api-key-for-tests-only"), "ApiKey")],
    ids=["jwt", "api-key"],
)
def test_auth_plugins_name_their_challenge(plugin, challenge):
    app = mk_app([whoami], plugins=[plugin])
    status, _, headers = call_wsgi(app, "/whoami", {}, with_headers=True)
    assert status.startswith("401") and headers["www-authenticate"] == challenge


def test_aiohttp_middlewares_name_their_challenge():
    from py2http.middleware import _unauthorized

    assert _unauthorized("x").headers["WWW-Authenticate"] == "Bearer"
    assert _unauthorized("x", "ApiKey").headers["WWW-Authenticate"] == "ApiKey"


# ---------------------------------------------------------------------------
# Adversarial-review regressions
# ---------------------------------------------------------------------------


class Eager(dict):
    def add(self, key):
        self[key] = "x" * 1_000
        return (k for k in [key])  # grows first, then returns a lazy result

    async def echo(self):
        got = None
        while True:
            got = yield got


def test_growth_before_returning_a_lazy_result_is_measured_at_return():
    store = Eager()
    func = _instance(store, max_obj_size=3, obj_sizeof=lambda obj, limit: len(obj))
    for i in range(3):
        as_owner("ann", func, _attr_name="add", key=i)  # never consumed
    with pytest.raises(InputError, match="size limit"):
        as_owner("ann", func, _attr_name="add", key=3)


def test_class_endpoint_drops_an_object_grown_before_a_lazy_return():
    func = _get_func_to_dispatch_handler(
        dict(
            endpoint=Eager,
            name="bag",
            attr_names="*",
            obj_owner=lambda req: req,
            max_obj_size=1,
            obj_sizeof=lambda obj, limit: len(obj),
        )
    )
    obj_id = as_owner("ann", func)
    as_owner("ann", func, _obj_id=obj_id, _attr_name="add", key=0)
    with pytest.raises(InputError, match="dropped"):
        as_owner("ann", func, _obj_id=obj_id, _attr_name="add", key=1)


def test_a_wrapped_async_generator_forwards_asend():
    func = _instance(Eager(), max_obj_size=None)

    async def drive():
        gen = as_owner("ann", func, _attr_name="echo")
        await gen.asend(None)
        got = await gen.asend(42)
        await gen.aclose()
        return got

    assert asyncio.run(drive()) == 42


def test_class_endpoint_readers_are_validated():
    with pytest.raises(ValueError, match="obj_readers"):
        _get_func_to_dispatch_handler(
            dict(
                endpoint=Store,
                name="bag",
                attr_names="*",
                obj_owner=lambda req: req,
                obj_readers=["raed"],
            )
        )


def test_a_challenge_with_a_line_break_falls_back_to_bearer(monkeypatch):
    from py2http.default_configs import www_authenticate_challenge

    monkeypatch.setenv("PY2HTTP_WWW_AUTHENTICATE", "Basic\r\nSet-Cookie: x=1")
    assert www_authenticate_challenge() == "Bearer"
