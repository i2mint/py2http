"""The Bottle auth plugins (``JWTPlugin``, ``ApiKeyAuthPlugin``) and the aiohttp
``mk_superadmin_middleware`` let valid credentials through and refuse the rest.

Bottle is the framework ``mk_app`` builds, so ``JWTPlugin`` is what guards a py2http
service; these tests go through a real ``mk_app`` app.
"""

import asyncio
import warnings

import jwt
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from py2http import mk_app
from py2http.bottle_plugins import ApiKeyAuthPlugin, JWTPlugin
from py2http.middleware import mk_superadmin_middleware
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
