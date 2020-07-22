from aiohttp import web
import json

from i2.errors import AuthorizationError, ForbiddenError, InputError, NotFoundError, DuplicateRecordError

from py2http.decorators import handle_json_req, send_json_resp


@handle_json_req
def default_input_mapper(input_kwargs):
    return input_kwargs


def default_input_validator(input_kwargs):
    return True


@send_json_resp
def default_output_mapper(output, input_kwargs):
    return output


def flask_output_mapper(output, input_kwargs):
    print(f'returning output: {output}')
    return output


def _raise_http_client_error(error, message):
    raise error(
        text=json.dumps({"error": message}), content_type="application/json"
    )


def default_error_handler(error, input_kwargs):
    message = str(error)
    if isinstance(error, (AuthorizationError, InputError, DuplicateRecordError)):
        _raise_http_client_error(web.HTTPBadRequest, message)
    elif isinstance(error, ForbiddenError):
        _raise_http_client_error(web.HTTPForbidden, message)
    elif isinstance(error, NotFoundError):
        _raise_http_client_error(web.HTTPNotFound, message)
    else:
        _raise_http_client_error(web.HTTPInternalServerError, message)


default_configs = {
    'app_name': 'OtoSense',
    'framework': 'aiohttp',
    'input_mapper': default_input_mapper,
    'input_validator': default_input_validator,
    'output_mapper': default_output_mapper,
    'error_handler': default_error_handler,
    'header_inputs': {},
    'middleware': [],
    'port': 3030,
    'http_method': 'post',
    'openapi': {}
}
