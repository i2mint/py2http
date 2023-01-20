from aiohttp import web
from bottle import response
import json
import os

from i2.errors import (
    AuthorizationError,
    ForbiddenError,
    InputError,
    NotFoundError,
    DuplicateRecordError,
)

from py2http.decorators import handle_json_req, send_json_resp, JsonRespEncoder
from py2http.config import AIOHTTP, BOTTLE, FLASK
from py2http.constants import JSON_CONTENT_TYPE

DFLT_CONTENT_TYPE = JSON_CONTENT_TYPE


@handle_json_req
def default_input_mapper(**inputs):
    return inputs


@send_json_resp
def default_output_mapper(output, **inputs):
    return output


def flask_output_mapper(output, **inputs):
    return output


def bottle_output_mapper(output, **inputs):
    response.content_type = JSON_CONTENT_TYPE
    return json.dumps(output, cls=JsonRespEncoder)


def _raise_http_client_error(error, message, reason=None):
    raise error(
        text=json.dumps({'error': message}),
        content_type=JSON_CONTENT_TYPE,
        reason=reason,
    )


def aiohttp_error_handler(error: Exception):
    message = str(error)
    if isinstance(error, (AuthorizationError, InputError, DuplicateRecordError)):
        _raise_http_client_error(
            web.HTTPBadRequest, message, reason=type(error).__name__
        )
    elif isinstance(error, ForbiddenError):
        _raise_http_client_error(web.HTTPForbidden, message)
    elif isinstance(error, NotFoundError):
        _raise_http_client_error(web.HTTPNotFound, message)
    else:
        message = 'Internal server error'
        _raise_http_client_error(web.HTTPInternalServerError, message)


def bottle_error_handler(error: Exception):
    message = str(error)
    if isinstance(error, (AuthorizationError, InputError, DuplicateRecordError)):
        response.status = f'400 {type(error).__name__}'
        # response.reason = type(error).__name__
    elif isinstance(error, ForbiddenError):
        response.status = 403
    elif isinstance(error, NotFoundError):
        response.status = 404
    else:
        response.status = 500
        if os.getenv('OPAQUE_ERRORS', None):
            message = 'Internal server error'
    return {'error': message}


def flask_error_handler(error: Exception):
    raise NotImplementedError()


def default_error_handler(error: Exception):
    framework = os.getenv('PY2HTTP_FRAMEWORK', BOTTLE)
    if framework == AIOHTTP:
        return aiohttp_error_handler(error)
    if framework == BOTTLE:
        return bottle_error_handler(error)
    if framework == FLASK:
        return flask_error_handler(error)
    return bottle_error_handler(error)


default_configs = {
    'app_name': 'HTTP Service',
    'framework': BOTTLE,
    'input_mapper': default_input_mapper,
    'output_mapper': default_output_mapper,
    'error_handler': default_error_handler,
    'header_inputs': {},
    'middleware': [],
    'host': 'localhost',
    'port': 3030,
    'server': 'gunicorn',
    'http_method': 'post',
    'openapi': {},
    'logger': None,
    'plugins': [],
    'enable_cors': False,
    'cors_allowed_origins': '*',
    'publish_openapi': False,
    'openapi_insecure': False,
    'publish_swagger': False,
    'swagger_url': '/swagger',
    'swagger_title': 'Swagger',
    'ssl_certfile': None,
    'ssl_keyfile': None,
}
