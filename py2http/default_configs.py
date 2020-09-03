from aiohttp import web
import json

from i2.errors import AuthorizationError, ForbiddenError, InputError, NotFoundError, DuplicateRecordError

from py2http.decorators import handle_json_req, send_json_resp, JsonRespEncoder


@handle_json_req
def default_input_mapper(inputs):
    return inputs


@send_json_resp
def default_output_mapper(output, inputs):
    return output


def flask_output_mapper(output, inputs):
    return output


def bottle_output_mapper(output, inputs):
    from bottle import response
    response.content_type = 'application/json'
    return json.dumps(output, cls=JsonRespEncoder)


def _raise_http_client_error(error, message, reason=None):
    raise error(
        text=json.dumps({"error": message}),
        content_type="application/json",
        reason=reason
    )


def default_error_handler(error, input_kwargs):
    message = str(error)
    if isinstance(error, (AuthorizationError, InputError, DuplicateRecordError)):
        _raise_http_client_error(web.HTTPBadRequest, message, reason=type(error).__name__)
    elif isinstance(error, ForbiddenError):
        _raise_http_client_error(web.HTTPForbidden, message)
    elif isinstance(error, NotFoundError):
        _raise_http_client_error(web.HTTPNotFound, message)
    else:
        _raise_http_client_error(web.HTTPInternalServerError, message)

def bottle_error_handler(error: Exception, input_kwargs):
    from bottle import response
    message = str(error)
    if isinstance(error, (AuthorizationError, InputError, DuplicateRecordError)):
        response.status = 400
    elif isinstance(error, ForbiddenError):
        response.status = 403
    elif isinstance(error, NotFoundError):
        response.status = 404
    else:
        response.status = 500
    return {'error': message}


default_configs = {
    'app_name': 'OtoSense',
    'framework': 'aiohttp',
    'input_mapper': default_input_mapper,
    'output_mapper': default_output_mapper,
    'error_handler': default_error_handler,
    'header_inputs': {},
    'middleware': [],
    'port': 3030,
    'http_method': 'post',
    'openapi': {},
    'logger': None,
    'plugins': [],
}
