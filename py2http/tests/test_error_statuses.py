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
from py2http.service import mk_flask_app
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


@pytest.mark.parametrize("error, status", CASES)
def test_flask_error_handler(error, status, monkeypatch):
    flask = pytest.importorskip("flask")
    monkeypatch.delenv("PY2HTTP_WWW_AUTHENTICATE", raising=False)
    monkeypatch.setenv("PY2HTTP_FRAMEWORK", "flask")
    from py2http.default_configs import default_error_handler

    app = flask.Flask(__name__)

    @app.route("/fail")
    def fail():
        return default_error_handler(error)

    response = app.test_client().get("/fail")
    assert response.status_code == status
    assert set(response.get_json()) == {"error"}
    if status == 400:  # as the bottle handler: the status line names the error
        assert response.status == f"400 {type(error).__name__}"
    if status == 401:
        assert response.headers["WWW-Authenticate"] == "Bearer"
    else:
        assert "WWW-Authenticate" not in response.headers
    if status == 500:
        assert "internal detail" in response.get_json()["error"]


def test_flask_opaque_errors_hides_500_text(monkeypatch):
    flask = pytest.importorskip("flask")
    monkeypatch.setenv("OPAQUE_ERRORS", "1")
    from py2http.default_configs import flask_error_handler

    app = flask.Flask(__name__)
    app.add_url_rule(
        "/f", "f", lambda: flask_error_handler(KeyError("internal detail"))
    )
    assert app.test_client().get("/f").get_json() == {"error": "Internal server error"}


@pytest.mark.parametrize("error, status", CASES)
def test_flask_app_statuses(error, status, monkeypatch, capsys):
    """``mk_app(framework='flask')``: statuses and challenges, end to end."""
    pytest.importorskip("flask")
    monkeypatch.delenv("PY2HTTP_WWW_AUTHENTICATE", raising=False)

    def fail():
        raise error

    app = mk_app([fail], framework="flask")
    response = app.test_client().post("/fail", json={})
    assert response.status_code == status
    assert set(response.get_json()) == {"error"}
    if status == 400:
        assert response.status == f"400 {type(error).__name__}"
    if status == 401:
        assert response.headers["WWW-Authenticate"] == "Bearer"
    else:
        assert "WWW-Authenticate" not in response.headers


def test_flask_app_answers_json():
    pytest.importorskip("flask")

    def add(a, b: int = 0):
        return {"sum": a + b}

    for app in (
        mk_app([add], framework="flask"),
        mk_flask_app([add]),  # called directly: still flask routes
    ):
        response = app.test_client().post("/add", json={"a": 1, "b": 2})
        assert response.status_code == 200
        assert response.content_type.startswith("application/json")
        assert response.get_json() == {"sum": 3}


def test_flask_does_not_leak_into_a_bottle_app(capsys):
    pytest.importorskip("flask")
    bottle_app = _app_raising(NotFoundError("x"))
    mk_app([_app_raising], framework="flask")  # sets the process-wide framework
    got, _ = call_wsgi(bottle_app, "/fail", {})
    assert got.startswith("404")  # still bottle's way of answering


def test_unsupported_framework_is_refused():
    with pytest.raises(NotImplementedError):
        mk_app([_app_raising], framework="django")


def test_flask_refuses_what_it_would_ignore():
    """An auth plugin dropped silently would leave the routes open."""
    pytest.importorskip("flask")
    for config in ({"plugins": [object()]}, {"enable_cors": True}):
        with pytest.raises(NotImplementedError):
            mk_app([_app_raising], framework="flask", **config)


def test_flask_openapi_only_when_published():
    pytest.importorskip("flask")

    def f():
        return 1

    assert mk_app([f], framework="flask").test_client().get("/openapi").status_code == 404
    published = mk_app([f], framework="flask", publish_openapi=True)
    assert published.test_client().get("/openapi").status_code == 200


def test_flask_middleware_wraps_the_wsgi_app():
    pytest.importorskip("flask")
    seen = []

    def wrap(wsgi_app):
        def wrapped(environ, start_response):
            seen.append(environ["PATH_INFO"])
            return wsgi_app(environ, start_response)

        return wrapped

    app = mk_app([_app_raising], framework="flask", middleware=[wrap])
    app.test_client().post("/_app_raising", json={})
    assert seen == ["/_app_raising"]
