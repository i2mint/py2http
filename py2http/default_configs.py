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
import inspect
import json
import logging
import os
from functools import wraps

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


def flask_json_output_mapper(output, **inputs):
    """The default output mapper of a Flask app: the output as a JSON response."""
    from flask import Response

    return Response(
        json.dumps(output, cls=JsonRespEncoder), content_type=JSON_CONTENT_TYPE
    )


flask_json_output_mapper.content_type = JSON_CONTENT_TYPE


def _flask_response(result, content_type):
    """``result`` as a Flask response of ``content_type`` if it is a ``str``/``bytes`` body, or
    a ``(body, status[, headers])`` tuple of one; anything else (a ``Response``, a dict) is kept.
    """
    from flask import Response
    from werkzeug.datastructures import Headers

    if isinstance(result, (str, bytes)):
        return Response(result, content_type=content_type)
    if isinstance(result, tuple) and result and isinstance(result[0], (str, bytes)):
        body, *rest = result
        status = rest[0] if rest and isinstance(rest[0], (int, str)) else None
        headers = next(
            (r for r in rest if r is not None and not isinstance(r, (int, str))), None
        )
        response = Response(body, status=status, headers=headers)
        if not any(
            k.lower() == "content-type" for k, _ in Headers(headers or {}).items()
        ):
            response.content_type = content_type
        return response
    return result


def flask_response_mapper(output_mapper):
    """Make a Flask view's response of what an output mapper returns.

    The ``send_*_resp`` decorators set Bottle's ``response.content_type`` and return
    the body (``str`` or ``bytes``); Flask ignores that and would answer ``text/html``.
    A mapper that declares a ``content_type`` and returns a ``str``/``bytes`` body, or a
    ``(body, status[, headers])`` tuple of one, gets that content type (unless the tuple's
    headers set their own); an ``async`` mapper is awaited first. Anything else (a
    ``Response``, a dict) is kept as is.

    >>> from py2http.decorators import send_raw_resp  # (needs flask)
    >>> flask_response_mapper(send_raw_resp(lambda o: o))(b"x").content_type  # doctest: +SKIP
    'text/plain'
    """
    content_type = getattr(output_mapper, "content_type", None)
    if content_type is None:
        return output_mapper

    if inspect.iscoroutinefunction(output_mapper):

        @wraps(output_mapper)
        async def mapper(output, **inputs):
            return _flask_response(await output_mapper(output, **inputs), content_type)

    else:

        @wraps(output_mapper)
        def mapper(output, **inputs):
            result = output_mapper(output, **inputs)
            if inspect.isawaitable(result):  # a sync wrapper around an async mapper

                async def settle():
                    return _flask_response(await result, content_type)

                return settle()
            return _flask_response(result, content_type)

    return mapper


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
    code = getattr(
        error, "code", None
    )  # werkzeug's own 4xx, e.g. 413 past MAX_CONTENT_LENGTH
    if (
        status == 500
        and isinstance(code, int)
        and 400 <= code < 500
        and hasattr(error, "get_response")
    ):
        status, message = code, getattr(error, "description", None) or message
    if status == 500 and os.getenv("OPAQUE_ERRORS", None):
        message = "Internal server error"
    status_line = f"400 {type(error).__name__}" if status == 400 else status
    headers = _status_headers(status)
    if hasattr(error, "get_response") and status == code:  # e.g. the ``Allow`` of a 405
        headers.update(
            (k, v)
            for k, v in error.get_response().headers
            if k.lower() not in ("content-type", "content-length")
        )
    return {"error": message}, status_line, headers


def default_error_handler(error: Exception):
    framework = os.getenv("PY2HTTP_FRAMEWORK", BOTTLE)
    if framework == AIOHTTP:
        return aiohttp_error_handler(error)
    if framework == BOTTLE:
        return bottle_error_handler(error)
    if framework == FLASK:
        return flask_error_handler(error)
    return bottle_error_handler(error)


# What the default mappers become under each framework (a mapper a user gave is kept)
_DEFAULT_ERROR_HANDLERS = {
    AIOHTTP: aiohttp_error_handler,
    BOTTLE: bottle_error_handler,
    FLASK: flask_error_handler,
}
_DEFAULT_OUTPUT_MAPPERS = {FLASK: flask_json_output_mapper}


def framework_defaults(framework, *, error_handler, output_mapper):
    """The error handler and output mapper to use under ``framework``: the given ones,
    except that the defaults (which only know of Bottle and AIOHTTP) are swapped for
    the framework's own, so that no process-wide state decides how a response is made.

    >>> framework_defaults(FLASK, error_handler=default_error_handler,
    ...     output_mapper=default_output_mapper)[0] is flask_error_handler
    True
    """
    if error_handler is default_error_handler:
        error_handler = _DEFAULT_ERROR_HANDLERS.get(framework, error_handler)
    if output_mapper is default_output_mapper:
        output_mapper = _DEFAULT_OUTPUT_MAPPERS.get(framework, output_mapper)
    if framework == FLASK:
        output_mapper = flask_response_mapper(output_mapper)
    return error_handler, output_mapper


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
    # Max bytes of a request body. Bottle: the in-memory limit (None keeps bottle's 100 KiB).
    # Flask: sets MAX_CONTENT_LENGTH (None keeps Flask's default: no limit).
    # A bigger request is answered "413 Request entity too large".
    "max_request_size": None,
    "cors_allowed_origins": "*",
    "publish_openapi": False,
    "openapi_insecure": False,
    "publish_swagger": False,
    "swagger_url": "/swagger",
    "swagger_title": "Swagger",
    "ssl_certfile": None,
    "ssl_keyfile": None,
}
