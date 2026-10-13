"""This module provides default configurations, input mappers, output mappers,
and error handlers for an HTTP service implemented in Python using the py2http
library. It includes functions for handling JSON requests and responses,
as well as mapping errors to appropriate HTTP responses based on different
HTTP frameworks (AIOHTTP, BOTTLE, FLASK).

The module also defines a set of default configuration values for setting up
the HTTP service, such as the application name, framework to use, port number,
error handling strategy, and CORS settings. It provides flexibility to customize
these configurations based on the specific requirements of the project.

Overall, this module serves as a foundational component for building and setting
up an HTTP service in Python using the py2http library."""

from aiohttp import web
from bottle import response
import json
import logging
import os

from i2.errors import (
    AuthorizationError,
    ForbiddenError,
    InputError,
    NotFoundError,
    DuplicateRecordError,
    OverwritesNotAllowed,
)

from py2http.decorators import handle_json_req, send_json_resp, JsonRespEncoder
from py2http.config import AIOHTTP, BOTTLE, FLASK
from py2http.constants import (
    BEARER_CHALLENGE,
    JSON_CONTENT_TYPE,
    WWW_AUTHENTICATE_ENV_VAR,
)

logger = logging.getLogger(__name__)

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


def _raise_http_client_error(error, message, reason=None, headers=None):
    raise error(
        text=json.dumps({"error": message}),
        content_type=JSON_CONTENT_TYPE,
        reason=reason,
        headers=headers,
    )


def www_authenticate_challenge() -> str:
    """The ``WWW-Authenticate`` value of a 401 a dispatched function raised: the
    ``PY2HTTP_WWW_AUTHENTICATE`` environment variable, else ``Bearer`` (also when the
    variable holds a line break, which would make every 401 fail to send).

    >>> os.environ.pop(WWW_AUTHENTICATE_ENV_VAR, None) and None
    >>> www_authenticate_challenge()
    'Bearer'
    """
    challenge = os.getenv(WWW_AUTHENTICATE_ENV_VAR)
    if not challenge:
        return BEARER_CHALLENGE
    if any(c in challenge for c in "\r\n\0"):
        logger.warning(
            "%s holds a control character; sending %r instead",
            WWW_AUTHENTICATE_ENV_VAR,
            BEARER_CHALLENGE,
        )
        return BEARER_CHALLENGE
    return challenge


def _status_headers(status: int) -> dict:
    return {"WWW-Authenticate": www_authenticate_challenge()} if status == 401 else {}


# HTTP status of each client error, most specific class first. ``ForbiddenError`` and
# ``OverwritesNotAllowed`` mean the client may not do this (403); any other
# ``AuthorizationError`` means the request did not say who it is (401).
_CLIENT_ERROR_STATUSES = (
    ((ForbiddenError, OverwritesNotAllowed), 403),
    (AuthorizationError, 401),
    ((InputError, DuplicateRecordError), 400),
    (NotFoundError, 404),
)
_AIOHTTP_ERRORS = {
    400: web.HTTPBadRequest,
    401: web.HTTPUnauthorized,
    403: web.HTTPForbidden,
    404: web.HTTPNotFound,
}


def error_status(error: Exception) -> int:
    """The HTTP status for an error a handler raised (500 when it is not a client's).

    >>> error_status(AuthorizationError()), error_status(ForbiddenError())
    (401, 403)
    >>> error_status(InputError()), error_status(KeyError())
    (400, 500)
    """
    for error_types, status in _CLIENT_ERROR_STATUSES:
        if isinstance(error, error_types):
            return status
    return 500


def aiohttp_error_handler(error: Exception):
    status = error_status(error)
    if status == 500:
        _raise_http_client_error(web.HTTPInternalServerError, "Internal server error")
    reason = type(error).__name__ if status == 400 else None
    _raise_http_client_error(
        _AIOHTTP_ERRORS[status],
        str(error),
        reason=reason,
        headers=_status_headers(status) or None,
    )


def bottle_error_handler(error: Exception):
    message = str(error)
    status = error_status(error)
    response.status = f"400 {type(error).__name__}" if status == 400 else status
    for header, value in _status_headers(status).items():
        response.set_header(header, value)
    if status == 500 and os.getenv("OPAQUE_ERRORS", None):
        message = "Internal server error"
    return {"error": message}


def flask_error_handler(error: Exception):
    """The ``(body, status, headers)`` a Flask view returns for an error, mapped like
    the bottle handler (``OPAQUE_ERRORS`` hides the text of a 500)."""
    message = str(error)
    status = error_status(error)
    if status == 500 and os.getenv("OPAQUE_ERRORS", None):
        message = "Internal server error"
    return {"error": message}, status, _status_headers(status)


def default_error_handler(error: Exception):
    framework = os.getenv("PY2HTTP_FRAMEWORK", BOTTLE)
    if framework == AIOHTTP:
        return aiohttp_error_handler(error)
    if framework == BOTTLE:
        return bottle_error_handler(error)
    if framework == FLASK:
        return flask_error_handler(error)
    return bottle_error_handler(error)


default_configs = {
    "app_name": "HTTP Service",
    "framework": BOTTLE,
    "input_mapper": default_input_mapper,
    "output_mapper": default_output_mapper,
    "error_handler": default_error_handler,
    "header_inputs": {},
    "middleware": [],
    "host": "localhost",
    "port": 3030,
    "server": "gunicorn",
    "http_method": "post",
    "openapi": {},
    "logger": None,
    "plugins": [],
    "enable_cors": False,
    "cors_allowed_origins": "*",
    "publish_openapi": False,
    "openapi_insecure": False,
    "publish_swagger": False,
    "swagger_url": "/swagger",
    "swagger_title": "Swagger",
    "ssl_certfile": None,
    "ssl_keyfile": None,
}
