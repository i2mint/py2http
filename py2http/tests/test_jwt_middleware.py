"""``mk_jwt_middleware`` verifies signatures, pins algorithms, and only lets named
public routes through without a token."""

import asyncio
import base64
import hashlib
import hmac
import json
import time

import jwt
import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from py2http.middleware import mk_jwt_middleware

SECRET = "s3cret-for-tests-only-0123456789abcdef"


async def _whoami(request):
    return web.json_response(getattr(request, "token", None))


async def ping(request):  # a handler whose __name__ is "ping", on a private route
    return web.json_response("private")


def _app(middleware):
    app = web.Application(middlewares=[middleware])
    app.router.add_get("/ping", _whoami, name="ping")
    app.router.add_get("/me", _whoami, name="me")
    app.router.add_get("/secret", ping)
    return app


def _get(middleware, path, token=None):
    """GET ``path`` on a fresh app (an aiohttp app is bound to one event loop)."""
    app = _app(middleware)

    async def go():
        headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
        async with TestClient(TestServer(app)) as client:
            resp = await client.get(path, headers=headers)
            return resp.status, await resp.text()

    return asyncio.run(go())


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _hs256_with_key(claims, key: bytes) -> str:
    """Sign by hand, so tests can forge what PyJWT itself refuses to produce."""
    signing_input = f"{_b64(json.dumps({'alg': 'HS256', 'typ': 'JWT'}).encode())}.{_b64(json.dumps(claims).encode())}"
    sig = hmac.new(key, signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64(sig)}"


def test_valid_token_is_decoded_onto_request():
    token = jwt.encode({"sub": "alice"}, SECRET, algorithm="HS256")
    status, body = _get(mk_jwt_middleware(SECRET), "/me", token)
    assert status == 200 and json.loads(body) == {"sub": "alice"}


@pytest.mark.parametrize(
    "token",
    [
        None,
        "",
        "garbage",
        jwt.encode(
            {"sub": "alice"}, "wrong-secret-0123456789abcdef0123", algorithm="HS256"
        ),
        _b64(b'{"alg":"none","typ":"JWT"}') + "." + _b64(b'{"sub":"alice"}') + ".",
        jwt.encode(
            {"sub": "alice", "exp": int(time.time()) - 60}, SECRET, algorithm="HS256"
        ),
        jwt.encode({"sub": "alice"}, SECRET, algorithm="HS512"),  # not an allowed alg
    ],
)
def test_bad_tokens_get_401_and_no_echo(token):
    status, body = _get(mk_jwt_middleware(SECRET), "/me", token)
    assert status == 401
    if token:
        assert token not in body


def test_public_routes_are_matched_by_route_name_not_handler_name():
    mw = mk_jwt_middleware(SECRET)
    assert _get(mw, "/ping")[0] == 200
    assert _get(mw, "/secret")[0] == 401  # handler is called "ping", route is not
    mw = mk_jwt_middleware(SECRET, public_routes=())
    assert _get(mw, "/ping")[0] == 401


def test_mixed_algorithm_families_need_explicit_opt_in():
    with pytest.raises(ValueError, match="algorithm-confusion"):
        mk_jwt_middleware(SECRET, algorithms=["HS256", "RS256"])
    with pytest.raises(ValueError):
        mk_jwt_middleware(SECRET, algorithms=[])
    mk_jwt_middleware(
        SECRET, algorithms=["HS256", "RS256"], allow_mixed_algorithm_families=True
    )


def test_algorithm_confusion_forgery_is_rejected_with_public_key_secret():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_pem = private.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    mw = mk_jwt_middleware(public_pem, algorithms=["RS256"])
    genuine = jwt.encode({"sub": "alice"}, private, algorithm="RS256")
    assert _get(mw, "/me", genuine)[0] == 200
    forged = _hs256_with_key({"sub": "mallory"}, public_pem)
    assert _get(mw, "/me", forged)[0] == 401


def test_verify_false_skips_signature_check():
    token = jwt.encode(
        {"sub": "alice"}, "another-secret-0123456789abcdef01", algorithm="HS256"
    )
    with pytest.warns(UserWarning):
        status, _ = _get(mk_jwt_middleware(SECRET, verify=False), "/me", "garbage")
    assert status == 200
    status, body = _get(mk_jwt_middleware(SECRET, verify=False), "/me", token)
    assert status == 200 and json.loads(body) == {"sub": "alice"}


@pytest.mark.parametrize(
    "kwargs, error",
    [
        ({"algorithms": "HS256"}, TypeError),
        ({"algorithms": ["hs256"]}, ValueError),
        ({"algorithms": ["none"]}, ValueError),
        ({"algorithms": ["RS256", "none"]}, ValueError),
    ],
)
def test_bad_algorithm_config_fails_at_construction(kwargs, error):
    with pytest.raises(error):
        mk_jwt_middleware(SECRET, **kwargs)


@pytest.mark.parametrize("secret", ["", b"", None])
def test_empty_secret_fails_at_construction(secret):
    with pytest.raises(ValueError):
        mk_jwt_middleware(secret)


def test_key_unfit_for_token_algorithm_is_401_not_500():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    public_pem = (
        rsa.generate_private_key(public_exponent=65537, key_size=2048)
        .public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    mw = mk_jwt_middleware(
        public_pem,
        algorithms=["HS256", "RS256"],
        allow_mixed_algorithm_families=True,
    )
    forged = _hs256_with_key({"sub": "mallory"}, public_pem)
    assert _get(mw, "/me", forged)[0] == 401


def test_none_in_public_routes_does_not_open_unnamed_routes():
    mw = mk_jwt_middleware(SECRET, public_routes=["ping", None])
    assert _get(mw, "/secret")[0] == 401
