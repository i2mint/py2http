"""The Bottle auth plugins (``JWTPlugin``, ``ApiKeyAuthPlugin``) and the aiohttp
``mk_superadmin_middleware`` let valid credentials through and refuse the rest.

Bottle is the framework ``mk_app`` builds, so ``JWTPlugin`` is what guards a py2http
service; these tests go through a real ``mk_app`` app.
"""

import asyncio
import base64
import json
import time
import warnings

import jwt
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from py2http import mk_app
from py2http.bottle_plugins import ApiKeyAuthPlugin, JWTPlugin
from py2http.middleware import mk_jwt_middleware, mk_superadmin_middleware
from py2http.service import current_request
from py2http.tests.utils_for_testing import call_wsgi

SECRET = "s3cret-for-tests-only-0123456789abcdef"
API_KEY = "api-key-for-tests-only"


def whoami():
    return getattr(current_request.get(), "token", None)


def other():
    return "other"


def _app(*plugins):
    return mk_app([whoami, other], plugins=list(plugins))


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _hs256_with_key(claims, key: bytes) -> str:
    """Sign by hand, so tests can forge what PyJWT itself refuses to produce."""
    import hashlib
    import hmac

    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    signing_input = f"{header}.{_b64(json.dumps(claims).encode())}"
    sig = hmac.new(key, signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64(sig)}"


def _token(claims=None, *, key=SECRET, algorithm="HS256"):
    return jwt.encode(claims or {"sub": "alice"}, key, algorithm=algorithm)


# ------------------------------------------------------------------- JWTPlugin


def test_jwt_valid_token_is_decoded_onto_request():
    status, body = call_wsgi(
        _app(JWTPlugin(SECRET)), "/whoami", {}, headers=_bearer(_token())
    )
    assert status.startswith("200") and body == {"sub": "alice"}


@pytest.mark.parametrize(
    "headers",
    [
        {},
        _bearer("garbage"),
        _bearer(_token(key="wrong-secret-0123456789abcdef0123")),
    ],
    ids=["no-header", "garbage", "wrong-signature"],
)
def test_jwt_bad_tokens_get_401(headers):
    status, _ = call_wsgi(_app(JWTPlugin(SECRET)), "/whoami", {}, headers=headers)
    assert status.startswith("401")


def test_jwt_mapper_renames_claims():
    plugin = JWTPlugin(SECRET, mapper={"sub": "user_id"})
    _, body = call_wsgi(_app(plugin), "/whoami", {}, headers=_bearer(_token()))
    assert body == {"user_id": "alice"}


def test_jwt_ignore_methods_and_ping_need_no_token():
    app = _app(JWTPlugin(SECRET, ignore_methods=["other"]))
    assert call_wsgi(app, "/other", {})[0].startswith("200")
    assert call_wsgi(app, "/ping", method="GET")[0].startswith("200")
    assert call_wsgi(app, "/whoami", {})[0].startswith("401")


def test_jwt_verify_false_lets_anything_through_with_a_warning():
    app = _app(JWTPlugin(SECRET, verify=False))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert call_wsgi(app, "/whoami", {}, headers=_bearer("garbage"))[0].startswith(
            "200"
        )
    assert caught
    unsigned = _token(key="another-secret-0123456789abcdef01")
    _, body = call_wsgi(app, "/whoami", {}, headers=_bearer(unsigned))
    assert body == {"sub": "alice"}


def test_jwt_rs256_with_public_key():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    app = _app(JWTPlugin(public_pem, algorithms=["RS256"]))
    genuine = _token(key=private, algorithm="RS256")
    assert call_wsgi(app, "/whoami", {}, headers=_bearer(genuine))[0].startswith("200")


# ------------------------------------------------------------- ApiKeyAuthPlugin


def test_api_key_plugin():
    app = _app(ApiKeyAuthPlugin(API_KEY))
    ok = call_wsgi(app, "/other", {}, headers={"Authorization": API_KEY})
    assert ok == ("200 OK", "other")
    for headers in ({}, {"Authorization": "nope"}):
        assert call_wsgi(app, "/other", {}, headers=headers)[0].startswith("401")


# ---------------------------------------------------- mk_superadmin_middleware


async def _hello(request):
    return web.json_response("hello")


def _aiohttp_get(middleware, headers):
    app = web.Application(middlewares=[middleware])
    app.router.add_get("/hello", _hello)

    async def go():
        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/hello", headers=headers)
            return resp.status

    return asyncio.run(go())


def test_superadmin_middleware():
    mw = mk_superadmin_middleware(API_KEY)
    assert _aiohttp_get(mw, {"Authorization": API_KEY}) == 200
    assert _aiohttp_get(mw, {"Authorization": "nope"}) == 401
    assert _aiohttp_get(mw, {}) == 401


# ------------------------------------- hardening (the sprint fixed these in the
# aiohttp middleware only; JWTPlugin is what guards an mk_app service)


def _rsa_keys():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return private, public_pem


@pytest.mark.parametrize(
    "token",
    [
        _token({"sub": "alice", "exp": int(time.time()) - 60}),  # expired
        _token(algorithm="HS512"),  # an algorithm not allowed
        _b64(b'{"alg":"none","typ":"JWT"}') + "." + _b64(b'{"sub":"alice"}') + ".",
    ],
    ids=["expired", "disallowed-alg", "alg-none"],
)
def test_jwt_rejected_tokens_are_401_not_500_and_not_echoed(token):
    status, body = call_wsgi(
        _app(JWTPlugin(SECRET)), "/whoami", {}, headers=_bearer(token)
    )
    assert status.startswith("401")
    assert token not in json.dumps(body)


def test_jwt_token_of_another_key_family_is_401():
    private, public_pem = _rsa_keys()
    app = _app(JWTPlugin(public_pem, algorithms=["RS256"]))
    assert call_wsgi(app, "/whoami", {}, headers=_bearer(_token()))[0].startswith("401")


def test_jwt_needs_the_bearer_scheme():
    app = _app(JWTPlugin(SECRET))
    headers = {"Authorization": f"Basic {_token()}"}
    assert call_wsgi(app, "/whoami", {}, headers=headers)[0].startswith("401")
    headers = {"Authorization": f"bearer {_token()}"}
    assert call_wsgi(app, "/whoami", {}, headers=headers)[0].startswith("200")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"secret": ""},  # would fail on every request instead
        {"secret": SECRET, "algorithms": ["HS256", "RS256"]},
        {"secret": SECRET, "algorithms": ["none"]},
    ],
)
def test_jwt_unsafe_setups_are_refused_at_construction(kwargs):
    with pytest.raises((ValueError, TypeError)):
        JWTPlugin(**kwargs)


def test_jwt_verify_false_needs_no_secret():
    JWTPlugin(verify=False)


def test_jwt_ignore_methods_with_published_openapi():
    """Routes py2http adds itself (``/openapi``) carry no ``method_name``."""
    app = mk_app(
        [whoami, other],
        plugins=[JWTPlugin(SECRET, ignore_methods=["other"])],
        publish_openapi=True,
    )
    status, _ = call_wsgi(app, "/openapi", method="GET", headers=_bearer(_token()))
    assert status.startswith("200")
    assert call_wsgi(app, "/openapi", method="GET")[0].startswith("401")


def test_jwt_and_api_key_plugins_stack():
    app = _app(JWTPlugin(SECRET, ignore_methods=["other"]), ApiKeyAuthPlugin(API_KEY))
    headers = {"Authorization": API_KEY}
    assert call_wsgi(app, "/other", {}, headers=headers)[0].startswith("200")


def test_cors_preflight_passes_without_token():
    app = mk_app([whoami], plugins=[JWTPlugin(SECRET)], enable_cors=True)
    status, _ = call_wsgi(app, "/whoami", method="OPTIONS")
    assert status.startswith("200")


@pytest.mark.parametrize("key", ["", None, b""])
def test_empty_api_keys_are_refused(key):
    with pytest.raises(ValueError):
        ApiKeyAuthPlugin(key)
    with pytest.raises(ValueError):
        mk_superadmin_middleware(key)


# ------------------------------------- adversarial-review findings, and #25


def _raw_get(app, path, raw_header: bytes):
    """GET with a raw (possibly non-UTF-8) ``Authorization`` header, as WSGI hands
    it over: latin-1 decoded bytes."""
    import io
    from wsgiref.util import setup_testing_defaults

    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": path,
        "HTTP_AUTHORIZATION": raw_header.decode("latin-1"),
        "wsgi.input": io.BytesIO(b""),
    }
    setup_testing_defaults(environ)
    statuses = []
    b"".join(app(environ, lambda status, headers, *a: statuses.append(status)))
    return statuses[0]


@pytest.mark.parametrize(
    "plugin",
    [JWTPlugin(SECRET), ApiKeyAuthPlugin(API_KEY)],
    ids=["jwt", "api-key"],
)
def test_non_utf8_authorization_header_is_401_not_500(plugin):
    app = mk_app([whoami], plugins=[plugin], http_method="get")
    assert _raw_get(app, "/whoami", b"Bearer \xe9.\xe9.\xe9").startswith("401")


def _aiohttp_raw_status(middleware, raw_header: bytes) -> int:
    """Send a raw (non-UTF-8) header over a socket, which aiohttp's client won't."""
    app = web.Application(middlewares=[middleware])
    app.router.add_get("/hello", _hello)

    async def go():
        async with TestServer(app) as server:
            reader, writer = await asyncio.open_connection(server.host, server.port)
            writer.write(
                b"GET /hello HTTP/1.1\r\nHost: x\r\nConnection: close\r\n"
                b"Authorization: " + raw_header + b"\r\n\r\n"
            )
            await writer.drain()
            status_line = await reader.readline()
            writer.close()
            return int(status_line.split()[1])

    return asyncio.run(go())


@pytest.mark.parametrize(
    "middleware",
    [mk_superadmin_middleware(API_KEY), mk_jwt_middleware(SECRET)],
    ids=["superadmin", "jwt"],
)
def test_aiohttp_non_utf8_authorization_header_is_401(middleware):
    assert _aiohttp_raw_status(middleware, b"Bearer \xe9.\xe9.\xe9") == 401


def test_mixed_families_are_fine_without_verification():
    JWTPlugin(verify=False, algorithms=["HS256", "RS256"])


def test_server_side_key_problem_is_logged(caplog):
    _, public_pem = _rsa_keys()
    plugin = JWTPlugin(
        public_pem, algorithms=["HS256", "RS256"], allow_mixed_algorithm_families=True
    )
    forged = _hs256_with_key({"sub": "mallory"}, public_pem)
    with caplog.at_level("WARNING", logger="py2http"):
        status, _ = call_wsgi(_app(plugin), "/whoami", {}, headers=_bearer(forged))
    assert status.startswith("401")
    assert "server-side reason" in caplog.text


@pytest.mark.parametrize("make", [JWTPlugin, mk_jwt_middleware])
def test_audience_passes_through_decode_kwargs(make):
    """A token with an ``aud`` claim needs ``decode_kwargs={'audience': ...}`` (#25)."""
    token = _token({"sub": "alice", "aud": "my-api"})
    if make is JWTPlugin:
        app = _app(JWTPlugin(SECRET, decode_kwargs={"audience": "my-api"}))
        assert (
            call_wsgi(app, "/whoami", {}, headers=_bearer(token))[1]["sub"] == "alice"
        )
        app = _app(JWTPlugin(SECRET))
        assert call_wsgi(app, "/whoami", {}, headers=_bearer(token))[0].startswith(
            "401"
        )
    with pytest.raises(ValueError, match="options"):
        make(SECRET, decode_kwargs={"options": {"verify_signature": False}})
