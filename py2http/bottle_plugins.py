from bottle import request, response, abort
import json
import jwt
from warnings import warn


class JWTPlugin:
    def __init__(self, secret: str, verify: bool = True):
        self._secret = secret
        self._verify = verify

    def __call__(self, handler):
        def wrapped_handler(*args, **kwargs):
            auth_header = request.headers.get('Authorization', '')
            token = auth_header[7:]
            try:
                decoded = jwt.decode(token, self._secret, verify=False)
                request.token = decoded
                return handler(*args, **kwargs)
            except jwt.DecodeError:
                if self._verify:
                    response.status = 401
                    response.content_type = 'application/json'
                    return json.dumps({'error': 'invalid authentication token'})
                warn(f'Invalid JWT: {token}')
                return handler(request)
        return wrapped_handler


class SuperadminAuthPlugin:
    def __init__(self, secret: str):
        self._secret = secret

    def __call__(self, handler):
        auth_header = request.headers.get('Authorization', '')
        if auth_header == self._secret:
            return handler(request)
        response.status = 401
        response.content_type = 'application/json'
        return json.dumps({'error': 'invalid API key'})
