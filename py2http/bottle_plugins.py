"""Plugins for adding middleware functionality to Bottle apps.
"""

from bottle import request, response, abort
from functools import wraps
import json
import jwt
from typing import Iterable
from warnings import warn
from py2http.constants import JSON_CONTENT_TYPE

OPTIONS = 'OPTIONS'


class JWTPlugin:
    """A plugin for validating JWTs and extracting their payloads.

    After optionally validating a JWT found in the request header, will assign a dict with the JWT claims
    to request.token.
    """

    def __init__(
        self,
        secret: str = '',
        verify: bool = True,
        mapper: dict = None,
        ignore_methods: Iterable[str] = None,
        algorithms: Iterable[str] = None,
    ):
        """Creates a new JWTPlugin instance.

        :param secret: (Optional) The JWT public key (RS256) or synchronous secret (HS256) used to validate tokens.
        :param verify: (Optional) If True, will verify JWT signatures against the provided secret,
        and reject unverified requests.
        :param mapper: (Optional) A dict that specifies how to map JWT claim value names in the output.
        :param ignore_methods: (Optional) A list of method names for the plugin to ignore.
        """
        self._secret = secret
        self._verify = verify
        self._mapper = mapper if mapper else {}
        self._ignore_methods = ignore_methods if ignore_methods else []
        self._algorithms = algorithms if algorithms else ['HS256']

    def __call__(self, handler):
        if self._ignore_methods and handler.method_name in self._ignore_methods:
            return handler

        @wraps(handler)
        def wrapped_handler(*args, **kwargs):
            if request.method == OPTIONS:
                return handler(*args, *kwargs)
            auth_header = request.headers.get('Authorization', '')
            token = auth_header[7:]
            try:
                decoded = jwt.decode(
                    token,
                    self._secret,
                    options={'verify_signature': self._verify},
                    algorithms=self._algorithms,
                )
                for k, v in self._mapper.items():
                    if k in decoded:
                        decoded[v] = decoded.pop(k)
                request.token = decoded
                return handler(*args, **kwargs)
            except jwt.DecodeError as error:
                if self._verify:
                    response.status = 401
                    response.content_type = JSON_CONTENT_TYPE
                    return json.dumps(
                        {
                            'error': f'Invalid authentication token "{token}", {str(error)}'
                        }
                    )
                warn(f'Invalid JWT: {token}')
                return handler(*args, **kwargs)

        return wrapped_handler


class ApiKeyAuthPlugin:
    def __init__(self, api_key: str):
        self._api_key = api_key

    def __call__(self, handler):
        def wrapped_handler(*args, **kwargs):
            auth_header = request.headers.get('Authorization', '')
            if auth_header == self._api_key:
                return handler(*args, **kwargs)
            response.status = 401
            response.content_type = JSON_CONTENT_TYPE
            return json.dumps({'error': 'invalid API key'})

        return wrapped_handler


# from https://stackoverflow.com/questions/17262170/bottle-py-enabling-cors-for-jquery-ajax-requests
# TODO: accept lists of headers and methods as init args
class CorsPlugin:
    def __init__(self, origins: str = '*'):
        self._origins = origins

    def __call__(self, handler):
        def wrapped_handler(*args, **kwargs):
            response.headers['Access-Control-Allow-Origin'] = self._origins
            response.headers[
                'Access-Control-Allow-Methods'
            ] = 'GET, POST, PUT, DELETE, OPTIONS'
            response.headers[
                'Access-Control-Allow-Headers'
            ] = 'Origin, Accept, Content-Type, X-Requested-With, Authorization, X-api-key'
            if request.method != OPTIONS:
                return handler(*args, **kwargs)

        return wrapped_handler
