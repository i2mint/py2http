import requests
from py2http.service import mk_http_service, mk_routes_and_openapi_specs, run_http_service
from http2py.py2request import mk_request_function
from py2http.util import ModuleNotFoundIgnore
from py2http.util import conditional_logger, CreateProcess
from inspect import signature
from collections.abc import Iterable


def mk_app_launcher(app, **kwargs):
    with ModuleNotFoundIgnore():
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


def get_client_funcs(funcs, p2h_configs=None, h2p_configs=None):
    routes, openapi_spec = mk_routes_and_openapi_specs(funcs, p2h_configs or {})
    return list(_w_funcs(funcs, openapi_spec, **(h2p_configs or {})))


def p2h2p_app(funcs, p2h_configs=None, h2p_configs=None):
    app = mk_http_service(funcs, **(p2h_configs or {}))
    w_funcs = list(_w_funcs(funcs, app.openapi_spec, **(h2p_configs or {})))
    app.funcs = funcs
    app.w_funcs = w_funcs
    return app


def run_service(funcs, configs=None):
    return run_http_service(funcs, **(configs or {}))


# equivalence tests ############################################


def test_p2h2p(funcs, inputs_for_func=None, p2h_configs=None, h2p_configs=None,
               check_signatures=False, wait_before_entering=2,
               verbose=False):
    """

    :param funcs: An iterable of callables
    :param inputs_for_func: a map from functions of func to an [(args, kwargs),...] list of valid inputs
    :param p2h_configs: py2http conversion configs
    :param h2p_configs: http2py conversion configs
    :param check_signatures:
    :param wait_before_entering:
    :return:
    """
    clog = conditional_logger(verbose)
    client_funcs = get_client_funcs(funcs, p2h_configs=p2h_configs, h2p_configs=h2p_configs)
    with CreateProcess(run_service, wait_before_entering=wait_before_entering, verbose=verbose,
                       funcs=funcs, configs=p2h_configs) as proc:
        for f, cf in zip(funcs, client_funcs):
            clog(f"{signature(f)} -- {signature(cf)}")
            if check_signatures:
                assert signature(f) == signature(cf)
            if isinstance(inputs_for_func, Iterable):
                for args, kwargs in inputs_for_func.get(f):
                    f_output = f(*args, **kwargs)
                    cf_output = cf(*args, **kwargs)
                    clog(f_output, cf_output.json())
                    assert f_output == cf_output


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


def square(x):
    return x * x


def power(x, p):
    result = 1
    for i in range(abs(p)):
        result = result * x if p > 0 else result / x
    return result


if __name__ == '__main__':
    # with run_server(run_example_service, wait_before_entering=0.5):
    #     example_test()

    funcs = [
        square,
        power
    ]
    inputs_for_func = {
        square: zip([(10,)], [{}]),
        power: zip([(10,), (5,)], [{}, {}])
    }
    test_p2h2p(funcs=funcs,
               inputs_for_func=inputs_for_func,
               verbose=True)
