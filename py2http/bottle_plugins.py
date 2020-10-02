from bottle import request, response, abort
import json
import jwt
from warnings import warn


class JWTPlugin:
    def __init__(self, secret: str, verify: bool = True, mapper: dict = None):
        self._secret = secret
        self._verify = verify
        self._mapper = mapper if mapper else {}

    def __call__(self, handler):
        def wrapped_handler(*args, **kwargs):
            auth_header = request.headers.get('Authorization', '')
            token = auth_header[7:]
            try:
                decoded = jwt.decode(token, self._secret, verify=False)
                for k, v in self._mapper.items():
                    if k in decoded:
                        decoded[v] = decoded.pop(k)
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


class ApiKeyAuthPlugin:
    def __init__(self, api_key: str):
        self._api_key = api_key

    def __call__(self, handler):
        def wrapped_handler(*args, **kwargs):
            print(f'headers: {dict(request.headers)}')
            auth_header = request.headers.get('Authorization', '')
            print(f'Expected {self._api_key}, got {auth_header}')
            if auth_header == self._api_key:
                return handler(*args, **kwargs)
            response.status = 401
            response.content_type = 'application/json'
            return json.dumps({'error': 'invalid API key'})
        return wrapped_handler
