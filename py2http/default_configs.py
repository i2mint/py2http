from aiohttp import web

from py2http.decorators import handle_json


@handle_json
def default_input_mapper(req_body):
    return req_body


def default_input_validator(input_kwargs):
    return True


def default_output_mapper(output, input_kwargs):
    return web.json_response(output)


default_configs = {
    'input_mapper': default_input_mapper,
    'input_validator': default_input_validator,
    'output_mapper': default_output_mapper,
    'middleware': [],
    'port': 3030,
    'http_method': 'post',
}
