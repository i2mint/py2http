"""The Bottle-only configs (auth ``plugins``, ``enable_cors``, ``publish_swagger``,
``openapi_insecure``) behave the same under Flask as under Bottle.

Each test runs once per framework, through a real ``mk_app`` app, so a divergence between
the two shows up as a failure of one parameter.
"""

import pytest

jwt = pytest.importorskip("jwt")
pytest.importorskip("flask")

from py2http import mk_app
from py2http.bottle_plugins import ApiKeyAuthPlugin, JWTPlugin
from py2http.service import current_request
from py2http.tests.utils_for_testing import call_wsgi

SECRET = "s3cret-for-tests-only-0123456789abcdef"
API_KEY = "api-key-for-tests-only"

frameworks = pytest.mark.parametrize("framework", ["bottle", "flask"])


def whoami():
    return getattr(current_request.get(), "token", None)


def other():
    return "other"


def _app(framework, **configs):
    return mk_app([whoami, other], framework=framework, **configs)


def _bearer(claims=None, *, key=SECRET):
    return {"Authorization": "Bearer " + jwt.encode(claims or {"sub": "alice"}, key)}


def _status(app, path, *, method="POST", headers=()):
    return call_wsgi(
        app, path, {} if method == "POST" else None, method=method, headers=headers
    )[0][:3]


# --------------------------------------------------------------------------- auth


@frameworks
def test_jwt_guards_routes_and_exposes_claims(framework):
    app = _app(framework, plugins=[JWTPlugin(SECRET, mapper={"sub": "user_id"})])
    status, body = call_wsgi(app, "/whoami", {}, headers=_bearer())
    assert status.startswith("200") and body == {"user_id": "alice"}
    assert _status(app, "/whoami") == "401"
    assert (
        _status(app, "/other", headers=_bearer(key="wrong-secret-0123456789abcdef0123"))
        == "401"
    )
    assert _status(app, "/other", headers={"Authorization": "Bearer garbage"}) == "401"


@frameworks
def test_unauthorized_answer_is_json_with_a_challenge(framework):
    app = _app(framework, plugins=[JWTPlugin(SECRET)])
    status, body, headers = call_wsgi(app, "/other", {}, with_headers=True)
    assert status.startswith("401") and "error" in body
    assert headers["www-authenticate"] == "Bearer"
    assert headers["content-type"].startswith("application/json")
    app = _app(framework, plugins=[ApiKeyAuthPlugin(API_KEY)])
    assert (
        call_wsgi(app, "/other", {}, with_headers=True)[2]["www-authenticate"]
        == "ApiKey"
    )


@frameworks
def test_ping_is_public_and_openapi_follows_openapi_insecure(framework):
    plugins = [JWTPlugin(SECRET)]
    app = _app(framework, plugins=plugins, publish_openapi=True)
    assert _status(app, "/ping", method="GET") == "200"
    assert _status(app, "/openapi", method="GET") == "401"
    app = _app(framework, plugins=plugins, publish_openapi=True, openapi_insecure=True)
    assert _status(app, "/openapi", method="GET") == "200"
    assert _status(app, "/other") == "401"  # the routes stay guarded


@frameworks
def test_ignore_methods_and_api_key(framework):
    app = _app(framework, plugins=[JWTPlugin(SECRET, ignore_methods=["other"])])
    assert _status(app, "/other") == "200"
    assert _status(app, "/whoami") == "401"
    app = _app(framework, plugins=[ApiKeyAuthPlugin(API_KEY)])
    assert _status(app, "/other", headers={"Authorization": API_KEY}) == "200"
    assert _status(app, "/other", headers={"Authorization": "nope"}) == "401"
    assert _status(app, "/other") == "401"


@frameworks
def test_every_plugin_must_pass(framework):
    app = _app(framework, plugins=[JWTPlugin(SECRET), ApiKeyAuthPlugin(API_KEY)])
    # a valid JWT is not the API key, and the key is not a JWT
    assert _status(app, "/other", headers=_bearer()) == "401"
    assert _status(app, "/other", headers={"Authorization": API_KEY}) == "401"


@frameworks
def test_unknown_paths_and_methods_are_not_views(framework):
    app = _app(framework, plugins=[JWTPlugin(SECRET)])
    assert _status(app, "/nowhere", method="GET") in ("404", "401")
    assert _status(app, "/other", method="GET") in ("405", "401")


def test_a_bottle_only_plugin_is_refused_under_flask():
    class Mine:
        def __call__(self, handler):
            return handler

    with pytest.raises(NotImplementedError, match="Bottle-only"):
        _app("flask", plugins=[Mine()])


# --------------------------------------------------------------------------- CORS


@frameworks
def test_cors_headers_on_answers_and_preflight(framework):
    app = _app(framework, enable_cors=True, cors_allowed_origins="https://a.example")
    _, _, headers = call_wsgi(app, "/other", {}, with_headers=True)
    assert headers["access-control-allow-origin"] == "https://a.example"
    assert "Authorization" in headers["access-control-allow-headers"]
    status, _, headers = call_wsgi(app, "/other", method="OPTIONS", with_headers=True)
    assert status.startswith("200")
    assert headers["access-control-allow-origin"] == "https://a.example"


@frameworks
def test_cors_off_adds_no_headers(framework):
    _, _, headers = call_wsgi(_app(framework), "/other", {}, with_headers=True)
    assert "access-control-allow-origin" not in headers


@frameworks
def test_cors_with_auth_preflight_open_and_refusals_carry_headers(framework):
    app = _app(framework, enable_cors=True, plugins=[ApiKeyAuthPlugin(API_KEY)])
    status, _, headers = call_wsgi(app, "/other", method="OPTIONS", with_headers=True)
    assert status.startswith("200") and "access-control-allow-origin" in headers
    status, _, headers = call_wsgi(app, "/other", {}, with_headers=True)
    assert status.startswith("401") and "access-control-allow-origin" in headers


# ------------------------------------------------------------------------ swagger


@frameworks
def test_swagger_is_served_when_published(framework):
    app = _app(
        framework, publish_openapi=True, publish_swagger=True, swagger_url="/docs"
    )
    assert _status(app, "/docs", method="GET") in ("200", "301", "302", "308")
    assert _status(_app(framework), "/docs", method="GET") == "404"


@frameworks
def test_swagger_is_guarded_by_the_plugins(framework):
    app = _app(
        framework,
        plugins=[ApiKeyAuthPlugin(API_KEY)],
        publish_swagger=True,
        swagger_url="/docs",
    )
    assert _status(app, "/docs/", method="GET") == "401"
