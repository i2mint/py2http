"""Errors a dispatched function raises become the HTTP status that names them."""

import pytest
from aiohttp import web
from i2.errors import (
    AuthorizationError,
    DuplicateRecordError,
    ForbiddenError,
    InputError,
    NotFoundError,
    OverwritesNotAllowed,
)

from py2http import mk_app
from py2http.default_configs import aiohttp_error_handler, error_status
from py2http.tests.utils_for_testing import call_wsgi

CASES = [
    (InputError("bad input"), 400),
    (DuplicateRecordError("dup"), 400),
    (AuthorizationError("who are you"), 401),
    (ForbiddenError("not you"), 403),
    (OverwritesNotAllowed("no overwrite"), 403),
    (NotFoundError("nothing here"), 404),
    (KeyError("internal detail"), 500),
]


def _app_raising(error):
    def fail():
        raise error

    return mk_app([fail])


@pytest.mark.parametrize("error, status", CASES)
def test_error_status(error, status):
    assert error_status(error) == status


@pytest.mark.parametrize("error, status", CASES)
def test_bottle_app_statuses(error, status, capsys):
    got, body = call_wsgi(_app_raising(error), "/fail", {})
    assert got.startswith(str(status))
    assert set(body) == {"error"}


def test_bottle_400_reason_names_the_error():
    got, _ = call_wsgi(_app_raising(InputError("x")), "/fail", {})
    assert got == "400 InputError"


def test_opaque_errors_hides_500_text(monkeypatch, capsys):
    monkeypatch.setenv("OPAQUE_ERRORS", "1")
    _, body = call_wsgi(_app_raising(KeyError("internal detail")), "/fail", {})
    assert body == {"error": "Internal server error"}


@pytest.mark.parametrize("error, status", CASES)
def test_aiohttp_error_handler(error, status):
    with pytest.raises(web.HTTPException) as caught:
        aiohttp_error_handler(error)
    assert caught.value.status == status
    if status == 500:
        assert "internal detail" not in caught.value.text
