from aiohttp import web
from json import JSONDecodeError
from warnings import warn


async def default_input_mapper(req):
    try:
        body = await req.json()
    except JSONDecodeError:
        warn('Invalid req body, expected JSON format.')
        body = {}
    if getattr(req, 'token', None):
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
    'middleware': [],
    'port': 3030,
}
