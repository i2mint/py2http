"""Plugins for adding middleware functionality to Bottle apps."""

import json
from functools import wraps
from typing import Iterable
from warnings import warn

from bottle import request, response

from py2http.auth import (
    DFLT_JWT_ALGORITHMS,
    CredentialsRejected,
    bearer_token,
    decode_jwt,
    jwt_algorithms,
    jwt_decode_kwargs,
    key_matches,
    required_key,
)
from py2http.constants import API_KEY_CHALLENGE, BEARER_CHALLENGE, JSON_CONTENT_TYPE

OPTIONS = "OPTIONS"


def _authorization_header() -> str:
    """The request's ``Authorization`` header; ``''`` if it is not valid UTF-8 (Bottle
    raises when decoding it), which every check then refuses."""
    try:
        return request.headers.get("Authorization", "")
    except UnicodeError:
        return ""


def _unauthorized(message, challenge=BEARER_CHALLENGE):
    response.status = 401
    response.set_header("WWW-Authenticate", challenge)
    response.content_type = JSON_CONTENT_TYPE
    return json.dumps({"error": message})


class JWTPlugin:
    """A plugin for validating JWTs and extracting their payloads.

    After optionally validating a JWT found in the request header, will assign a dict with the JWT claims
    to request.token.
    """

    def __init__(
        self,
        secret: str = "",
        verify: bool = True,
        mapper: dict = None,
        ignore_methods: Iterable[str] = None,
        algorithms: Iterable[str] = None,
        *,
        allow_mixed_algorithm_families: bool = False,
        decode_kwargs: dict = None,
    ):
        """Creates a new JWTPlugin instance.

        :param secret: The JWT public key (RS256) or shared secret (HS256) used to
            validate tokens. Required (non-empty) when ``verify`` is True.
        :param verify: (Optional) If True, will verify JWT signatures against the provided secret,
        and reject unverified requests.
        :param mapper: (Optional) A dict that specifies how to map JWT claim value names in the output.
        :param ignore_methods: (Optional) A list of method names for the plugin to ignore.
        :param algorithms: (Optional) The algorithms a token may be signed with
            (default ``("HS256",)``); validated as ``py2http.auth.jwt_algorithms``
            describes, as is ``allow_mixed_algorithm_families``.
        :param decode_kwargs: (Optional) Extra ``jwt.decode`` arguments, such as
            ``audience``, ``issuer`` or ``leeway``.
        """
        self._secret = secret
        self._verify = verify
        self._mapper = mapper if mapper else {}
        self._ignore_methods = ignore_methods if ignore_methods else []
        self._algorithms = jwt_algorithms(
            secret,
            verify=verify,
            algorithms=algorithms or DFLT_JWT_ALGORITHMS,
            allow_mixed_algorithm_families=allow_mixed_algorithm_families,
        )
        self._decode_kwargs = jwt_decode_kwargs(decode_kwargs)

    challenge = BEARER_CHALLENGE

    def _claims(self, authorization_header):
        """The (renamed) claims of the token in the header; raises ``CredentialsRejected``."""
        decoded = decode_jwt(
            bearer_token(authorization_header),
            self._secret,
            algorithms=self._algorithms,
            verify=self._verify,
            decode_kwargs=self._decode_kwargs,
        )
        for k, v in self._mapper.items():
            if k in decoded:
                decoded[v] = decoded.pop(k)
        return decoded

    def authenticate(self, authorization_header, *, method, endpoint):
        """The claims to put on the request (``None`` when there are none to put), or
        ``CredentialsRejected``. Framework-independent: the Bottle plugin and the Flask
        ``before_request`` hook (``py2http.flask_plugins``) both call it."""
        if method == OPTIONS or endpoint in self._ignore_methods:
            return None
        try:
            return self._claims(authorization_header)
        except CredentialsRejected as rejection:
            if self._verify:
                raise
            warn(f"Invalid JWT: {rejection.__cause__}")
            return None

    def __call__(self, handler):
        if getattr(handler, "method_name", None) in self._ignore_methods:
            return handler

        @wraps(handler)
        def wrapped_handler(*args, **kwargs):
            try:
                claims = self.authenticate(
                    _authorization_header(),
                    method=request.method,
                    endpoint=getattr(handler, "method_name", None),
                )
            except CredentialsRejected as rejection:
                return _unauthorized(str(rejection))
            if claims is not None:
                request.token = claims
            return handler(*args, **kwargs)

        return wrapped_handler


class ApiKeyAuthPlugin:
    """A plugin letting through only requests whose ``Authorization`` header is
    exactly ``api_key`` (compared in constant time; an empty key is refused)."""

    challenge = API_KEY_CHALLENGE

    def __init__(self, api_key: str):
        self._api_key = required_key(api_key)

    def authenticate(self, authorization_header, *, method, endpoint):
        """``None`` (the key sets nothing on the request) if the header is the key,
        else ``CredentialsRejected``. Framework-independent, like ``JWTPlugin``'s."""
        if not key_matches(authorization_header, self._api_key):
            raise CredentialsRejected("invalid API key")

    def __call__(self, handler):
        @wraps(handler)
        def wrapped_handler(*args, **kwargs):
            try:
                self.authenticate(
                    _authorization_header(), method=request.method, endpoint=None
                )
            except CredentialsRejected as rejection:
                return _unauthorized(str(rejection), self.challenge)
            return handler(*args, **kwargs)

        return wrapped_handler


# from https://stackoverflow.com/questions/17262170/bottle-py-enabling-cors-for-jquery-ajax-requests
# TODO: accept lists of headers and methods as init args
class CorsPlugin:
    def __init__(self, origins: str = "*"):
        self._origins = origins

    def __call__(self, handler):
        @wraps(handler)
        def wrapped_handler(*args, **kwargs):
            response.headers["Access-Control-Allow-Origin"] = self._origins
            response.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, PUT, DELETE, OPTIONS"
            )
            response.headers["Access-Control-Allow-Headers"] = (
                "Origin, Accept, Content-Type, X-Requested-With, Authorization, X-api-key"
            )
            if request.method != OPTIONS:
                return handler(*args, **kwargs)

        return wrapped_handler
