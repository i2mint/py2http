import requests
from py2http.service import (
    mk_app,
    mk_routes_and_openapi_specs,
    run_app,
)
from http2py.py2request import mk_request_func_from_openapi_spec
from py2http.util import ModuleNotFoundIgnore
from py2http.util import conditional_logger, run_process
from py2http.openapi_utils import OpenApiExtractor
from inspect import signature
from collections.abc import Iterable


# def mk_app_launcher(app, **kwargs):
#     with ModuleNotFoundIgnore():
#         from aiohttp.web import Application, run_app
#         if isinstance(app, Application):
#             def app_launcher(app):
#                 port = kwargs.pop('port', getattr(app, 'port', None))
#                 return run_app(app, port=port, **kwargs)
#
#             return app_launcher
#         else:
#             raise TypeError(f"Unknown app type ({type(app)}): {app}")


def client_funcs_from_openapi(openapi_spec, **h2p_configs):
    e = OpenApiExtractor(openapi_spec)

    for (path, method), spec in e.paths_and_methods_items():
        yield mk_request_func_from_openapi_spec(
            path, openapi_spec, method, **h2p_configs
        )


def get_client_funcs(funcs, p2h_configs=None, h2p_configs=None):
    routes, openapi_spec = mk_routes_and_openapi_specs(funcs, **(p2h_configs or {}))
    return list(client_funcs_from_openapi(openapi_spec, **(h2p_configs or {})))


def p2h2p_app(funcs, p2h_configs=None, h2p_configs=None):
    app = mk_app(funcs, **(p2h_configs or {}))
    # w_funcs = list(_w_funcs(funcs, app.openapi_spec, **(h2p_configs or {})))
    c_funcs = list(client_funcs_from_openapi(app.openapi_spec, **(h2p_configs or {})))
    app.funcs = funcs
    app.c_funcs = c_funcs
    return app


#
# def run_service(funcs, configs=None):
#     return run_app(funcs, **(configs or {}))


# equivalence tests ############################################


def p2h2p_test(
    funcs,
    inputs_for_func=None,
    p2h_configs=None,
    h2p_configs=None,
    check_signatures=False,
    wait_before_entering=2,
    verbose=False,
):
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
    client_funcs = get_client_funcs(
        funcs, p2h_configs=p2h_configs, h2p_configs=h2p_configs
    )
    with run_process(
        func=run_app,
        func_args=(funcs,),
        func_kwargs=dict({}, configs=p2h_configs),
        is_ready=wait_before_entering,
        verbose=verbose,
    ) as proc:
        for f, cf in zip(funcs, client_funcs):
            clog(f'{signature(f)} -- {signature(cf)}')
            if check_signatures:
                assert signature(f) == signature(cf)
            if isinstance(inputs_for_func, Iterable):
                for args, kwargs in inputs_for_func.get(f):
                    f_output = f(*args, **kwargs)
                    cf_output = cf(*args, **kwargs)
                    assert f_output == cf_output


dflt_port = '3030'
dflt_root_url = 'http://localhost'
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


def power(x, p=1):
    result = 1
    for i in range(abs(p)):
        result = result * x if p > 0 else result / x
    return result


def test_types(str='', int=0, float=0.0, list=[], dict={}, bool=True):
    pass


if __name__ == '__main__':

    funcs = [
        square,
        power,
        # test_types
    ]
    inputs_for_func = {
        square: zip([(10,)], [{}]),
        power: zip([(10,), (5,)], [{'p': 1}, {'p': 2}]),
    }

    p2h2p_test(funcs=funcs, inputs_for_func=inputs_for_func, verbose=True)
