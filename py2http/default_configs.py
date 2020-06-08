from aiohttp import web
from json import JSONDecodeError
import jwt
from warnings import warn


def jwt_reader_middleware(req, handler):
    auth_header = req.headers.get('Authorization', '')
    token = auth_header[7:]
    if not token:
        return handler(req)
    try:
        decoded = jwt.decode(token, verify=False)
        req.token = decoded
        return handler(req)
    except jwt.DecodeError:
        warn(f'Invalid JWT: {token}')
        return handler(req)


async def default_input_mapper(req):
    try:
        body = await req.json()
    except JSONDecodeError:
        warn('Invalid req body, expected JSON format.')
        body = {}
    if req.getattr('token', None):
        body = dict(body, **req.token)
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
