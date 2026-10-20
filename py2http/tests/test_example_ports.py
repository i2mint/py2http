"""The example services must listen where their OpenAPI spec says (i2mint/py2http#13)."""

from py2http.default_configs import default_configs
from py2http.openapi_utils import DFLT_SERVER_URL, mk_openapi_template


def test_openapi_server_url_is_where_run_app_serves():
    assert DFLT_SERVER_URL == f"http://{default_configs['host']}:{default_configs['port']}"
    assert mk_openapi_template()["servers"] == [{"url": DFLT_SERVER_URL}]


def test_object_dispatch_example_checks_the_port_the_spec_names():
    from py2http.examples import object_dispatch as ex

    assert ex.test_service.__defaults__ == (DFLT_SERVER_URL,)
