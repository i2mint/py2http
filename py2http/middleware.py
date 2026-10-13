"""
py2http is a Python module that allows you to dispatch Python functions as HTTP
services.
By running a basic HTTP service from a list of functions, you can access OpenAPI
specifications, Swagger documentation, and utilize the HTTP service's routes.
Additionally, Py2http provides features for method transformation, input mapping,
output mapping, error handling, and client generation.

The code snippet provided below is a part of Py2http module and includes middleware
functions for handling JWT authentication and superadmin authorization.
These middleware functions are designed to be used within the Py2http framework to
ensure secure and authenticated access to HTTP routes.

Include the following docstring to describe this module:
"Middleware functions for handling JWT authentication and superadmin authorization
within the Py2http framework. These functions ensure secure access to HTTP routes
by verifying credentials and permissions. Use these middleware functions to enforce
authentication and control access to web resources.
"""

import json
from collections.abc import Iterable
from warnings import warn

from py2http.constants import JSON_CONTENT_TYPE

DFLT_JWT_ALGORITHMS = ("HS256",)
DFLT_PUBLIC_ROUTES = ("ping", "openapi")


def _algorithm_family(algorithm: str) -> str:
    """The key family an algorithm verifies with: a shared secret for ``HS*``, a
    public key otherwise.

    >>> _algorithm_family('HS512'), _algorithm_family('RS256'), _algorithm_family('ES256')
    ('hmac', 'public-key', 'public-key')
    """
    return "hmac" if algorithm.upper().startswith("HS") else "public-key"


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
        verify: If False, signatures are NOT checked and an invalid token only
            triggers a warning; for development only.
        algorithms: The algorithms a token may be signed with. Defaults to
            ``("HS256",)``, as ``py2http.bottle_plugins.JWTPlugin`` does.
        public_routes: Names of aiohttp routes (``name=`` in ``add_route``) that
            need no token. Matched on the route name, not the handler's
            ``__name__``, so a handler that happens to be called ``ping`` is not
            public by accident.
        allow_mixed_algorithm_families: Accepting an HMAC algorithm and a
            public-key algorithm with one ``secret`` is the classic
            algorithm-confusion setup (a token "signed" with HS256 using the
            public key as the HMAC secret), so it raises ``ValueError`` unless
            this is True. The middleware used to accept ``["HS256", "RS256"]``;
            pass that list with this flag to restore it.
    """
    import jwt
    from aiohttp import web

    algorithms = list(algorithms)
    if not algorithms:
        raise ValueError("algorithms must name at least one JWT algorithm")
    families = {_algorithm_family(a) for a in algorithms}
    if len(families) > 1 and not allow_mixed_algorithm_families:
        raise ValueError(
            f"algorithms={algorithms} mixes HMAC and public-key algorithms with one "
            "secret, which allows algorithm-confusion forgeries; use one family, or "
            "pass allow_mixed_algorithm_families=True if you really mean it"
        )
    public_routes = frozenset(public_routes)

    def _unauthorized(message):
        return web.HTTPUnauthorized(
            text=json.dumps({"error": message}),
            content_type=JSON_CONTENT_TYPE,
        )

    @web.middleware
    async def middleware(req, handler):
        route = req.match_info.route
        if getattr(route, "name", None) in public_routes:
            return await handler(req)
        auth_header = req.headers.get("Authorization", "")
        token = auth_header[7:] if auth_header[:7].lower() == "bearer " else ""
        try:
            decoded = jwt.decode(
                token,
                secret,
                options={"verify_signature": verify},
                algorithms=algorithms,
            )
        except jwt.InvalidTokenError as error:
            if verify:
                raise _unauthorized(f"Invalid authentication token: {error}")
            warn(f"Invalid JWT: {error}")
            return await handler(req)
        req.token = decoded
        return await handler(req)

    return middleware


def mk_superadmin_middleware(secret):
    from aiohttp import web

    @web.middleware
    async def middleware(req, handler):
        auth_header = req.headers.get("Authorization", "")
        if auth_header == secret:
            return await handler(req)
        return web.HTTPUnauthorized(
            text=json.dumps({"error": "invalid API key"}),
            content_type=JSON_CONTENT_TYPE,
        )

    return middleware
