from aiohttp import web
from json import JSONDecodeError
import jwt
from warnings import warn


def jwt_reader_middleware(request, handler):
    auth_header = req.headers.get('Authorization', '')
    token = auth_header[7:]
    if not token:
        return handler(request)
    try:
        decoded = jwt.decode(token, verify=False)
        request.token = decoded
        return handler(request)
    except jwt.DecodeError:
        warn(f'Invalid JWT: {token}')
        return handler(request)


async def default_input_mapper(request):
    try:
        body = await request.json()
    except JSONDecodeError:
        warn('Invalid request body, expected JSON format.')
        body = {}
    if request.getattr('token', None):
        body = dict(body, **request.token)
    return [], body


def default_input_validator(input):
    return True


def default_output_mapper(output):
    return web.json_response(output)


default_configs = {
    'input_mapper': default_input_mapper,
    'input_validator': default_input_validator,
    'output_mapper': default_output_mapper,
    'middleware': [jwt_reader_middleware],
}
