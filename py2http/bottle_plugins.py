from bottle import request, response, abort
import json
import jwt
from warnings import warn

OPTIONS = 'OPTIONS'


class JWTPlugin:
    def __init__(self, secret: str, verify: bool = True, mapper: dict = None):
        self._secret = secret
        self._verify = verify
        self._mapper = mapper if mapper else {}

    def __call__(self, handler):
        def wrapped_handler(*args, **kwargs):
            if request.method == OPTIONS:
                return handler(*args, *kwargs)
            auth_header = request.headers.get('Authorization', '')
            token = auth_header[7:]
            try:
                decoded = jwt.decode(
                    token, self._secret, options={'verify_signature': False}
                )
                for k, v in self._mapper.items():
                    if k in decoded:
                        decoded[v] = decoded.pop(k)
                request.token = decoded
                return handler(*args, **kwargs)
            except jwt.DecodeError as error:
                if self._verify:
                    response.status = 401
                    response.content_type = 'application/json'
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
            response.content_type = 'application/json'
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
