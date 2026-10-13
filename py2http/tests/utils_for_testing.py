"""Helpers shared by py2http's tests: calling a WSGI app in-process, and running a
dispatched function as if a given request (or owner) were being handled."""

import io
import json
from contextlib import contextmanager
from multiprocessing.context import Process
from time import sleep
from wsgiref.util import setup_testing_defaults

from py2http.util import conditional_logger, deprecate


@contextmanager
@deprecate
def run_server(launcher, wait_before_entering=0, verbose=False, **kwargs):
    """Context manager to launch server on entry, and shut it down on exit"""

    clog = conditional_logger(verbose)
    server = None
    try:
        server = Process(target=launcher, kwargs=kwargs)
        clog(f"Starting server...")
        server.start()
        clog(f"... server started.")
        sleep(wait_before_entering)
        yield server
    finally:
        if server is not None and server.is_alive():
            clog(f"Terminating server...")
            server.terminate()
        clog(f"... server terminated")


def call_wsgi(
    app, path, payload=None, *, method="POST", headers=(), with_headers=False
):
    """Send one request to the WSGI ``app`` in-process; return ``(status, body)``, the
    body decoded from JSON when it is JSON (``(status, body, response_headers)`` with
    ``with_headers``, header names lower-cased).

    ``headers`` maps header names (``"Authorization"``) to values.
    """
    body = b"" if payload is None else json.dumps(payload).encode()
    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "CONTENT_TYPE": "application/json",
        "CONTENT_LENGTH": str(len(body)),
        "wsgi.input": io.BytesIO(body),
    }
    for name, value in dict(headers).items():
        environ["HTTP_" + name.upper().replace("-", "_")] = value
    setup_testing_defaults(environ)
    statuses, response_headers = [], {}

    def start_response(status, headers, *a):
        statuses.append(status)
        response_headers.update((k.lower(), v) for k, v in headers)  # case-insensitive

    out = b"".join(app(environ, start_response))
    try:
        body = json.loads(out)
    except ValueError:
        body = out.decode()
    if with_headers:
        return statuses[0], body, response_headers
    return statuses[0], body


def as_owner(owner, func, **kwargs):
    """Call ``func(**kwargs)`` while ``owner`` is the request being handled, so an
    ``obj_owner=lambda req: req`` hook sees ``owner``."""
    from py2http.service import current_request

    token = current_request.set(owner)
    try:
        return func(**kwargs)
    finally:
        current_request.reset(token)
