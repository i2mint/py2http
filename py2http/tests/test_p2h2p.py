from py2http.service import mk_http_service
from http2py.py2request import mk_request_function
from py2http.util import ModuleNotFoundIgnore
# from py2http.tests.utils_for_testing import run_server
from inspect import signature


def mk_app_launcher(app, **kwargs):
    with ModuleNotFoundIgnore:
        from aiohttp.web import Application, run_app
        if isinstance(app, Application):
            def app_launcher(app):
                port = kwargs.pop('port', getattr(app, 'port', None))
                return run_app(app, port=port, **kwargs)

            return app_launcher
        else:
            raise TypeError(f"Unknown app type ({type(app)}): {app}")


def _w_funcs(funcs, openapi_spec, **h2p_configs):
    def func_to_path(func):  # TODO: Fragile. Need to make func <-> path more robust (e.g. include in openapi_spec)
        return '/' + func.__name__

    # def get_props_for_func(func):
    #     path = func_to_path(func)
    #     t = openapi_spec["paths"][func_to_path(func)]
    #     t = t.get('post', t.get('get', None))  # make more robust
    #     assert t is not None
    #     # TODO: glommify
    #     return t['requestBody']['content']['application/json']['schema']['properties']

    for func in funcs:
        # openapi_props = get_props_for_func(func)
        yield mk_request_function.from_openapi_spec(
            func_to_path(func), openapi_spec, **h2p_configs)


def p2h2p_app(funcs, p2h_configs=None, h2p_configs=None):
    app = mk_http_service(funcs, **(p2h_configs or {}))
    w_funcs = list(_w_funcs(funcs, app.openapi_spec, **(h2p_configs or {})))
    app.funcs = funcs
    app.w_funcs = w_funcs
    return app


# equivalence tests ############################################
inputs_for_func = ...  #


def test_p2h2p(funcs, inputs_for_func=None, p2h_configs=None, h2p_configs=None,
               check_signatures=False, wait_before_entering=2):
    """

    :param funcs: An iterable of callables
    :param inputs_for_func: a map from functions of func to an [(args, kwargs),...] list of valid inputs
    :param p2h_configs: py2http conversion configs
    :param h2p_configs: http2py conversion configs
    :param check_signatures:
    :param wait_before_entering:
    :return:
    """
    inputs_for_func = inputs_for_func or {}
    app = p2h2p_app(funcs, p2h_configs=p2h_configs, h2p_configs=h2p_configs)
    with run_server(mk_app_launcher(app), wait_before_entering=wait_before_entering):
        for f, ff in zip(funcs, app.w_funcs):
            if check_signatures:
                assert signature(f) == signature(ff)
            for args, kwargs in inputs_for_func.get(f):
                f_output = f(*args, **kwargs)
                ff_output = ff(*args, **kwargs)
                assert f_output == ff_output


import requests

dflt_port = '3030'
dflt_root_url = "http://localhost"
dflt_base_url = dflt_root_url + ':' + dflt_port


def example_test(base_url=dflt_base_url):
    add_result = requests.post(f'{base_url}/add', json={'a': 10, 'b': 5})
    assert str(add_result.json()) == '15'

    multiply_result = requests.post(f'{base_url}/multiply', json={'multiplier': 6})
    assert str(multiply_result.json()) == '30'

    no_args_result = requests.post(f'{base_url}/no_args', json={})
    assert str(no_args_result.json()) == 'no args'


if __name__ == '__main__':
    from py2http.tests.utils_for_testing import run_server
    from py2http.tests.example_service import example_functions, run_http_service


    def run_example_service():
        return run_http_service(example_functions)


    with run_server(run_example_service, wait_before_entering=0.5):
        example_test()
