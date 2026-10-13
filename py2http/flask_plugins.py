"""Flask counterparts of the Bottle plugins: auth as a ``before_request`` hook, CORS as an
``after_request`` hook.

The credential checks are the plugins' own (``JWTPlugin.authenticate``,
``ApiKeyAuthPlugin.authenticate``, which call ``py2http.auth``), so Bottle and Flask
refuse the same requests for the same reasons. A plugin without an ``authenticate``
method is a Bottle-only plugin: it is refused with ``NotImplementedError`` rather than
dropped, because a silently dropped auth plugin would leave its routes open.
"""

import json
from collections.abc import Iterable

from py2http.auth import CredentialsRejected
from py2http.constants import JSON_CONTENT_TYPE

OPTIONS = "OPTIONS"
_CORS_METHODS = "GET, POST, PUT, DELETE, OPTIONS"
_CORS_HEADERS = (
    "Origin, Accept, Content-Type, X-Requested-With, Authorization, X-api-key"
)


def check_flask_plugins(plugins: Iterable | None) -> list:
    """The ``plugins`` as a list, each known to work under Flask; else ``NotImplementedError``.

    >>> check_flask_plugins(None)
    []
    >>> check_flask_plugins([object()])  # doctest: +ELLIPSIS
    Traceback (most recent call last):
      ...
    NotImplementedError: The plugin <object object at ...> is Bottle-only...
    """
    plugins = list(plugins or ())
    for plugin in plugins:
        if not callable(getattr(plugin, "authenticate", None)):
            raise NotImplementedError(
                f"The plugin {plugin!r} is Bottle-only: under the framework 'flask' only "
                "plugins with an `authenticate(authorization_header, *, method, "
                "endpoint)` method (JWTPlugin, ApiKeyAuthPlugin) are supported"
            )
    return plugins


def _unauthorized(message: str, challenge: str):
    from flask import Response

    response = Response(
        json.dumps({"error": message}), status=401, content_type=JSON_CONTENT_TYPE
    )
    response.headers["WWW-Authenticate"] = challenge
    return response


def mk_auth_hook(plugins: list, *, public_endpoints: Iterable[str], cors: bool = False):
    """A ``before_request`` function running ``plugins`` (outermost first, as under Bottle).

    Everything is guarded except: the ``public_endpoints``; a request that matched no
    route (it answers 404/405, as under Bottle, and runs no view); and, with ``cors``,
    the ``OPTIONS`` preflight, which Bottle's CORS plugin answers before any auth runs.
    A plugin's claims go on ``request.token``, where the endpoint finds them through
    ``current_request``.
    """
    from flask import request

    public = frozenset(public_endpoints)

    def authenticate_request():
        endpoint = request.endpoint
        if endpoint is None or endpoint in public:
            return None
        if cors and request.method == OPTIONS:
            return None
        try:
            header = request.headers.get("Authorization", "")
        except UnicodeError:  # a header that is not text is refused by every check
            header = ""
        for plugin in plugins:
            try:
                claims = plugin.authenticate(
                    header, method=request.method, endpoint=endpoint
                )
            except CredentialsRejected as rejection:
                return _unauthorized(str(rejection), plugin.challenge)
            if claims is not None:
                request.token = claims
        return None

    return authenticate_request


def mk_cors_hook(origins: str = "*"):
    """An ``after_request`` function adding the CORS headers ``CorsPlugin`` adds.

    Flask answers the ``OPTIONS`` preflight itself, so this only adds the headers.
    """

    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = origins
        response.headers["Access-Control-Allow-Methods"] = _CORS_METHODS
        response.headers["Access-Control-Allow-Headers"] = _CORS_HEADERS
        return response

    return add_cors_headers
