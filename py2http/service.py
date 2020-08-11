from aiohttp import web
import asyncio
from collections import namedtuple
from copy import deepcopy
from flask import Flask, request
from functools import partial
from inspect import isawaitable
import json
from typing import Callable
from types import FunctionType

from i2.errors import InputError

from py2http.config import mk_config, FLASK, AIOHTTP
from py2http.default_configs import default_configs
from py2http.openapi_utils import add_paths_to_spec, mk_openapi_path, mk_openapi_template
from py2http.schema_tools import mk_input_schema_from_func, mk_output_schema_from_func
from py2http.util import TypeAsserter


def method_not_found(method_name):
    raise web.HTTPNotFound(text=json.dumps({'error': f'method {method_name} not found'}),
                           content_type='application/json')


# default TypeAsserter used in this project
assert_type = TypeAsserter(types_for_kind={
    'input_mapper': Callable,
    'output_mapper': Callable,
})


def func_copy(func):
    new_func = FunctionType(func.__code__, func.__globals__, func.__name__,
                            func.__defaults__, func.__closure__)
    new_func.__dict__.update(deepcopy(func.__dict__))
    return new_func


def mk_route(func, **configs):
    """
    Generate an aiohttp route object and an OpenAPI path specification for a function

    :param func: The function

    :Keyword Arguments: The configuration settings
    """

    # TODO: perhaps collections.abc.Mapping initialized with func, configs, etc.
    config_for = partial(mk_config, func=func, configs=configs, defaults=default_configs)
    framework = config_for('framework')
    input_mapper = config_for('input_mapper')
    output_mapper = config_for('output_mapper')
    error_handler = config_for('error_handler')
    header_inputs = config_for('header_inputs', type=dict)

    exclude_request_keys = header_inputs.keys()
    request_schema = getattr(input_mapper, 'request_schema', None)
    if request_schema is None:
        request_schema = mk_input_schema_from_func(func, exclude_keys=exclude_request_keys)
    response_schema = getattr(output_mapper,
                              'response_schema',
                              mk_output_schema_from_func(output_mapper))
    if not response_schema:
        response_schema = getattr(func,
                                  'response_schema',
                                  mk_output_schema_from_func(func))

    async def handle_request(req):
        input_kwargs = {}
        try:
            inputs = input_mapper(req, request_schema)
            if isawaitable(inputs):  # Pattern: pass-on async property
                inputs = await inputs
            if isinstance(inputs, dict):
                input_args = ()
                input_kwargs = inputs
            elif isinstance(inputs, list):
                input_args = tuple(inputs)
                input_kwargs = {}
            elif isinstance(inputs, tuple):
                input_args = inputs[0]
                input_kwargs = inputs[1]
            try:
                raw_result = func(*input_args, **input_kwargs)
            except TypeError as error:
                raise InputError(str(error))
            if isawaitable(raw_result):  # Pattern: pass-on async property
                raw_result = await raw_result

            final_result = output_mapper(raw_result, input_kwargs)
            if isawaitable(final_result):
                final_result = await final_result
            if framework == AIOHTTP and not isinstance(final_result, web.Response):
                final_result = web.json_response(final_result)
            return final_result
        except Exception as error:
            return error_handler(error, input_kwargs)

    # TODO: Align config keys and variable names
    valid_http_methods = {'get', 'put', 'post', 'delete'}  # outside function
    http_method = config_for('http_method')  # read
    assert isinstance(http_method, str)  # validation
    http_method = http_method.lower()  # normalization
    assert http_method in valid_http_methods  # validation

    def mk_framework_route(http_method, path, method_name, handler):
        if framework == AIOHTTP:
            web_mk_route = getattr(web, http_method)
            return web_mk_route(path, handler)
        if framework == FLASK:
            def sync_handle_request():
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(handler(request))
                return result
            sync_handle_request.path = path
            sync_handle_request.http_method = http_method
            sync_handle_request.method_name = method_name
            return sync_handle_request
        return None

    # TODO: Make func -> path a function (not hardcoded)
    # TODO: Make sure that func -> path MAPPING is known outside (perhaps through openapi)
    method_name = config_for('name') or func.__name__
    path = config_for('route') or f'/{method_name}'

    route = mk_framework_route(http_method, path, method_name, handle_request)

    path_fields = dict({'x-method_name': method_name}, **extra_path_info(func))
    openapi_path = mk_openapi_path(path,
                                   http_method,
                                   request_schema=request_schema,
                                   response_schema=response_schema,
                                   path_fields=path_fields)

    return route, openapi_path


def extra_path_info(func):
    return {}


def handle_ping(req):
    # the req param is required for this function to work as an aiohttp route
    # even though it's not used, so don't remove it
    return web.json_response({'ping': 'pong'})


def run_http_service(funcs, **configs):
    """
    Launches an HTTP server, with a list of functions as route handlers.

    See config.yaml for configuration documentation.
    """
    app = mk_http_service(funcs, **configs)
    port = configs.get('port', app.dflt_port)
    framework = mk_config('framework', None, configs, default_configs)
    if framework == FLASK:
        return run_flask_service(app, port)
    if framework == AIOHTTP:
        return run_aiohttp_service(app, port)


def run_flask_service(app, port):
    app.run(port=port, debug=True)


def run_aiohttp_service(app, port):
    web.run_app(app, port=port)


def mk_http_service(funcs, **configs):
    routes, openapi_spec = mk_routes_and_openapi_specs(funcs, configs)
    framework = mk_config('framework', None, configs, default_configs)
    if framework == FLASK:
        return mk_flask_service(routes, openapi_spec, **configs)
    return mk_aiohttp_service(routes, openapi_spec, **configs)


def mk_flask_service(routes, openapi_spec, **configs):
    app_name = mk_config('app_name', None, configs, default_configs)
    app = Flask(app_name)
    for route in routes:
        app.add_url_rule(route.path, route.method_name, route, methods=[route.http_method.upper()])
    app.openapi_spec = openapi_spec
    app.dflt_port = mk_config('port', None, configs, default_configs)
    return app


def mk_aiohttp_service(routes, openapi_spec, **configs):
    middleware = mk_config('middleware', None, configs, default_configs)
    app = web.Application(middlewares=middleware)
    app.add_routes([web.get('/ping', handle_ping), *routes])
    # adding a few more attributes
    app.openapi_spec = openapi_spec
    app.dflt_port = mk_config('port', None, configs, default_configs)
    return app


# TODO: Make signature explicit instead of using configs
#   What it needs from config is only: openapi_spec and a header_inputs
#   Make the user of this function get those from general configs
def mk_routes_and_openapi_specs(funcs, configs):
    routes = []
    openapi_config = mk_config('openapi', None, configs, default_configs, type=dict)
    openapi_spec = mk_openapi_template(openapi_config)
    header_inputs = mk_config('header_inputs', None, configs, default_configs)
    if header_inputs:
        openapi_spec['x-header-inputs'] = header_inputs
    for func in funcs:
        # sig = inspect.signature(func)  # commenting out because not used
        route, openapi_path = mk_route(func, **configs)
        routes.append(route)
        add_paths_to_spec(openapi_spec['paths'], openapi_path)
    openapi_filename = openapi_config.get('filename', None)
    if openapi_filename:
        with open(openapi_filename, 'w') as fp:
            json.dump(openapi_spec, fp)
    return routes, openapi_spec


def run_many_services(apps, **configs):
    app = web.Application()
    for route, subapp in apps.items():
        app.add_subapp(route, subapp)
    port = mk_config('port', None, configs, default_configs)
    web.run_app(app, port=port)


##########################################################################################
###### Old pieces of code, kept around until we're sure we don't want them any more #######


def mk_config_nt(keys, *args, **kwargs):
    """Return a namedtuple of objects created by mk_config for several keys (and same configs).

    Advantages:

    Can use ths way:

    ```
    args, validator, postproc = mk_config_nt(['args', 'validator', 'postproc'], **configs)
    ```

    Or this way (useful when we're dealing with many items):

    ```
    c = mk_config_nt(['args', 'validator', 'postproc'], **configs)
    c.args
    c.validator
    c.postproc
    ```

    Namedtuple attribute access is as fast as a dict (if not faster in 3.8).
    One disadvantage, over a custom object is that it's contents are immutable
    (if we use the `c.attr` form -- the unpacking form is fine since we're dealing
    with copies).

    """
    ConfigNT = namedtuple('ConfigNT', field_names=keys)
    return ConfigNT(**{k: mk_config(k, *args, **kwargs) for k in keys})

    # input_mapper = mk_config('input_mapper', func, configs, default_configs)
    # output_mapper = mk_config('output_mapper', func, configs, default_configs)
    # header_inputs = mk_config('header_inputs', func, configs, default_configs, type=dict)

    # 1: Replacement proposal
    # input_mapper, output_mapper, header_inputs = mk_config_nt(
    #     ['input_mapper', 'output_mapper', 'header_inputs'],
    #     func, configs, default_configs)
    # input_mapper, output_mapper, header_inputs = mk_configs(
    #     ['input_mapper', 'output_mapper', 'header_inputs'],
    #     func, configs, default_configs
    # )
    # 1: To replace this   # TODO: Test and choose
    # input_mapper = mk_config('input_mapper', func, configs, default_configs)
    # output_mapper = mk_config('output_mapper', func, configs, default_configs)
    # header_inputs = mk_config('header_inputs', func, configs, default_configs)
