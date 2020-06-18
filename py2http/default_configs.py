from aiohttp import web

from py2http.decorators import handle_json_req, send_json_resp


@handle_json_req
def default_input_mapper(req_body):
    return req_body


def default_input_validator(input_kwargs):
    return True


@send_json_resp
def default_output_mapper(output, input_kwargs):
    return output


default_configs = {
    'input_mapper': default_input_mapper,
    'input_validator': default_input_validator,
    'output_mapper': default_output_mapper,
    'header_inputs': {},
    'middleware': [],
    'port': 3030,
    'http_method': 'post',
    'openapi': {}
}
