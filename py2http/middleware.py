"""aiohttp middleware that guards every route of an app: ``mk_jwt_middleware``
(a verified ``Authorization: Bearer`` JWT) and ``mk_superadmin_middleware`` (one
shared key). The checks themselves live in ``py2http.auth``, shared with the Bottle
plugins of ``py2http.bottle_plugins``."""

import json
from collections.abc import Iterable
from warnings import warn

from py2http.auth import (
    DFLT_JWT_ALGORITHMS,
    CredentialsRejected,
    _algorithm_family,  # noqa: F401  (was defined here)
    _names,
    bearer_token,
    decode_jwt,
    jwt_algorithms,
    key_matches,
    required_key,
)
from py2http.constants import JSON_CONTENT_TYPE

DFLT_PUBLIC_ROUTES = ("ping", "openapi")


def _unauthorized(message):
    from aiohttp import web

    return web.HTTPUnauthorized(
        text=json.dumps({"error": message}), content_type=JSON_CONTENT_TYPE
    )


def mk_jwt_middleware(
    secret,
    verify=True,
    *,
    algorithms: Iterable[str] = DFLT_JWT_ALGORITHMS,
    public_routes: Iterable[str] = DFLT_PUBLIC_ROUTES,
    allow_mixed_algorithm_families: bool = False,
):
    """Make an aiohttp middleware that requires a valid ``Authorization: Bearer``
    JWT on every request, and puts the decoded claims on ``request.token``.

    Args:
        secret: The key tokens are verified with (an HMAC secret for ``HS*``
            algorithms, a public key for ``RS*``/``ES*``/...).
        verify: If False, signatures and claims (``exp``, ...) are NOT checked:
            whatever a token says ends up on ``request.token``, and an
            undecodable token only triggers a warning. For development only.
            (Before, PyJWT 2 ignored the legacy option this passed, so
            signatures were still checked even with ``verify=False``.)
        algorithms: The algorithms a token may be signed with (PyJWT names,
            case-sensitive; ``"none"`` is refused). Defaults to ``("HS256",)``,
            as ``py2http.bottle_plugins.JWTPlugin`` does.
        public_routes: Names of aiohttp routes (``name=`` in ``add_route``) that
            need no token. Matched on the route name, not the handler's
            ``__name__``, so a handler that happens to be called ``ping`` is not
            public by accident. Route names are matched in sub-applications
            too, so a sub-app route named ``ping`` is public as well.
        allow_mixed_algorithm_families: Accepting an HMAC algorithm and a
            public-key algorithm with one ``secret`` is the classic
            algorithm-confusion setup (a token "signed" with HS256 using the
            public key as the HMAC secret), so it raises ``ValueError`` unless
            this is True. The middleware used to accept ``["HS256", "RS256"]``;
            pass that list with this flag to restore it.
    """
    from aiohttp import web

    algorithms = jwt_algorithms(
        secret,
        verify=verify,
        algorithms=algorithms,
        allow_mixed_algorithm_families=allow_mixed_algorithm_families,
    )
    public_routes = frozenset(
        name for name in _names("public_routes", public_routes) if name is not None
    )

    @web.middleware
    async def middleware(req, handler):
        route = req.match_info.route
        if getattr(route, "name", None) in public_routes:
            return await handler(req)
        token = bearer_token(req.headers.get("Authorization"))
        try:
            req.token = decode_jwt(token, secret, algorithms=algorithms, verify=verify)
        except CredentialsRejected as rejection:
            if verify:
                raise _unauthorized(str(rejection)) from None
            warn(f"Invalid JWT: {rejection.__cause__}")
        return await handler(req)

    return middleware


def mk_superadmin_middleware(secret):
    """Make an aiohttp middleware that only lets through requests whose
    ``Authorization`` header is exactly ``secret`` (compared in constant time).
    An empty ``secret`` is refused, since it would let header-less requests through.
    """
    from aiohttp import web

    secret = required_key(secret, name="secret")

    @web.middleware
    async def middleware(req, handler):
        if key_matches(req.headers.get("Authorization"), secret):
            return await handler(req)
        raise _unauthorized("invalid API key")

    return middleware
