from aiohttp import web
import asyncio
from collections import namedtuple
from copy import deepcopy
from functools import partial
from inspect import isawaitable
import json
from typing import Callable
from types import FunctionType
import logging
import os
from bottle import Bottle
import traceback

from i2.errors import InputError, DataError, AuthorizationError

from py2http.bottle_plugins import CorsPlugin, OPTIONS
from py2http.config import mk_config, FLASK, AIOHTTP, BOTTLE
from py2http.default_configs import default_configs
from py2http.openapi_utils import (
    add_paths_to_spec,
    mk_openapi_path,
    mk_openapi_template,
)
from py2http.schema_tools import (
    mk_input_schema_from_func,
    mk_output_schema_from_func,
)
from py2http.util import TypeAsserter


def method_not_found(method_name):
    raise web.HTTPNotFound(
        text=json.dumps({'error': f'method {method_name} not found'}),
        content_type='application/json',
    )


# default TypeAsserter used in this project
assert_type = TypeAsserter(
    types_for_kind={'input_mapper': Callable, 'output_mapper': Callable,}
)


def func_copy(func) -> Callable:
    new_func = FunctionType(
        func.__code__,
        func.__globals__,
        func.__name__,
        func.__defaults__,
        func.__closure__,
    )
    new_func.__dict__.update(deepcopy(func.__dict__))
    return new_func


def mk_route(func, **configs):
    """
    Generate an route object and an OpenAPI path specification for a function

    :param func: The function

    :Keyword Arguments: The configuration settings
    """

    def get_input_args_and_kwargs(inputs):
        input_args = ()
        input_kwargs = {}
        if isinstance(inputs, dict):
            input_kwargs = inputs
        elif isinstance(inputs, list):
            input_args = tuple(inputs)
        elif isinstance(inputs, tuple):
            input_args = inputs[0]
            input_kwargs = inputs[1]
        return input_args, input_kwargs

    # TODO: perhaps collections.abc.Mapping initialized with func, configs, etc.
    config_for = partial(
        mk_config, func=func, configs=configs, defaults=default_configs
    )
    framework = _get_framework(configs, default_configs)
    input_mapper = config_for('input_mapper')
    output_mapper = config_for('output_mapper')
    error_handler = config_for('error_handler')
    header_inputs = config_for('header_inputs', type=dict)
    logger = config_for('logger')

    exclude_request_keys = header_inputs.keys()
    request_schema = getattr(input_mapper, 'request_schema', None)
    if request_schema is None:
        request_schema = mk_input_schema_from_func(
            func, exclude_keys=exclude_request_keys
        )
    response_schema = getattr(
        output_mapper,
        'response_schema',
        mk_output_schema_from_func(output_mapper),
    )
    if not response_schema:
        response_schema = getattr(
            func, 'response_schema', mk_output_schema_from_func(func)
        )

    def handle_error(func):
        def handle_request(req):
            try:
                return func(req)
            except (DataError, AuthorizationError, InputError) as error:
                if logger:
                    level = (
                        logging.INFO
                        if logger.getEffectiveLevel() >= logging.INFO
                        else logging.DEBUG
                    )
                    exc_info = level == logging.DEBUG
                    logger.log(
                        level, traceback.format_exc(), exc_info=exc_info
                    )
                else:
                    print(traceback.format_exc())
                return error_handler(error)
            except Exception as error:
                print(traceback.format_exc())
                if logger:
                    logger.exception(error)
                return error_handler(error)

        return handle_request

    @handle_error
    def sync_handle_request(req):
        if framework == BOTTLE:
            req.get_json = lambda *x: req.json
        inputs = input_mapper(req, request_schema)
        input_args, input_kwargs = get_input_args_and_kwargs(inputs)
        try:
            raw_result = func(*input_args, **input_kwargs)
        except TypeError as error:
            raise InputError(str(error))

        return output_mapper(raw_result, input_kwargs)

    @handle_error
    async def aiohttp_handle_request(req):
        inputs = input_mapper(req, request_schema)
        if isawaitable(inputs):  # Pattern: pass-on async property
            inputs = await inputs
        input_args, input_kwargs = get_input_args_and_kwargs(inputs)
        try:
            raw_result = func(*input_args, **input_kwargs)
        except TypeError as error:
            raise InputError(str(error))
        if isawaitable(raw_result):  # Pattern: pass-on async property
            raw_result = await raw_result

        final_result = output_mapper(raw_result, input_kwargs)
        if isawaitable(final_result):
            final_result = await final_result
        if not isinstance(final_result, web.Response):
            final_result = web.json_response(final_result)
        return final_result

    #  TODO: Align config keys and variable names
    valid_http_methods = {'get', 'put', 'post', 'delete'}  # outside function
    http_method = config_for('http_method')  # read
    assert isinstance(http_method, str)  # validation
    http_method = http_method.lower()  # normalization
    assert http_method in valid_http_methods  # validation

    def mk_framework_route(http_method, path, method_name):
        if framework == AIOHTTP:
            web_mk_route = getattr(web, http_method)
            return web_mk_route(path, aiohttp_handle_request)
        else:
            if framework == FLASK:
                from flask import request
            elif framework == BOTTLE:
                from bottle import request

            def handle_request(*args):
                result = sync_handle_request(request)
                if isawaitable(result):
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    result = loop.run_until_complete(result)
                return result

            handle_request.path = path
            handle_request.http_method = http_method
            handle_request.method_name = method_name
            return handle_request

    # TODO: Make func -> path a function (not hardcoded)
    # TODO: Make sure that func -> path MAPPING is known outside (perhaps through openapi)
    method_name = config_for('name') or func.__name__
    path = config_for('route') or f'/{method_name}'

    route = mk_framework_route(http_method, path, method_name)

    path_fields = dict({'x-method_name': method_name}, **extra_path_info(func))
    openapi_path = mk_openapi_path(
        path,
        http_method,
        request_schema=request_schema,
        response_schema=response_schema,
        path_fields=path_fields,
    )

    return route, openapi_path


def extra_path_info(func):
    return {'description': func.__doc__}


def run_http_service(funcs, **configs):
    """
    Launches an HTTP server, with a list of functions as route handlers.

    See config.yaml for configuration documentation.
    """
    app = mk_http_service(funcs, **configs)
    port = configs.get('port', app.dflt_port)
    framework = _get_framework(configs, default_configs)
    if framework == FLASK:
        return run_flask_service(app, port)
    if framework == BOTTLE:
        return run_bottle_service(app, port)
    return run_aiohttp_service(app, port)


def run_flask_service(app, port):
    app.run(port=port, debug=True)


def run_bottle_service(app, port):
    app.run(port=port, debug=True)


def run_aiohttp_service(app, port):
    web.run_app(app, port=port)


def mk_http_service(funcs, **configs):
    """
    Generates an HTTP service object
    """

    def handle_ping_sync():
        return {'ping': 'pong'}

    def handle_ping_async(req):
        # the req param is required for this function to work as an aiohttp route
        # even though it's not used, so don't remove it
        return web.json_response({'ping': 'pong'})

    def get_openapi_sync():
        return openapi_spec

    def get_openapi_async(req):
        return web.json_response(openapi_spec)

    def mk_flask_service():
        from flask import Flask

        app_name = mk_config('app_name', None, configs, default_configs)
        app = Flask(app_name)
        middleware = mk_config('middleware', None, configs, default_configs)
        # publish_openapi = mk_config('publish_openapi', None, configs, default_configs)
        if middleware:
            app = middleware(app)
        for route in routes:
            app.add_url_rule(
                route.path,
                route.method_name,
                route,
                methods=[route.http_method.upper()],
            )
        app.add_url_rule('/ping', 'ping', handle_ping_sync)
        app.add_url_rule('/openapi', 'openapi', get_openapi_sync)
        app.openapi_spec = openapi_spec
        app.dflt_port = mk_config('port', None, configs, default_configs)
        return app

    def mk_bottle_service():
        app = Bottle(catchall=False)
        enable_cors = mk_config('enable_cors', None, configs, default_configs)
        plugins = mk_config('plugins', None, configs, default_configs)
        if enable_cors:
            cors_allowed_origins = mk_config(
                'cors_allowed_origins', None, configs, default_configs
            )
            app.install(CorsPlugin(cors_allowed_origins))
        publish_openapi = mk_config(
            'publish_openapi', None, configs, default_configs
        )
        openapi_insecure = mk_config(
            'openapi_insecure', None, configs, default_configs
        )
        if plugins:
            for plugin in plugins:
                app.install(plugin)
        for route in routes:
            route_http_method = route.http_method.upper()
            http_methods = (
                route.http_method
                if not enable_cors
                else [OPTIONS, route_http_method]
            )
            # print(f'Mounting route: {route.path} {route.http_method.upper()}')
            app.route(route.path, http_methods, route, route.method_name)
        app.route(
            path='/ping', callback=handle_ping_sync, name='ping', skip=plugins
        )
        if publish_openapi:
            skip = plugins if openapi_insecure else None
            app.route(
                path='/openapi',
                callback=get_openapi_sync,
                name='openapi',
                skip=skip,
            )
        app.openapi_spec = openapi_spec
        app.dflt_port = mk_config('port', None, configs, default_configs)
        return app

    def mk_aiohttp_service():
        middleware = mk_config('middleware', None, configs, default_configs)
        app = web.Application(middlewares=middleware)
        app.add_routes(
            [
                web.get('/ping', handle_ping_async, name='ping'),
                web.get('/openapi', get_openapi_async, name='openapi'),
                *routes,
            ]
        )
        # adding a few more attributes
        app.openapi_spec = openapi_spec
        app.dflt_port = mk_config('port', None, configs, default_configs)
        return app

    routes, openapi_spec = mk_routes_and_openapi_specs(funcs, **configs)
    framework = _get_framework(configs, default_configs)
    if framework == FLASK:
        return mk_flask_service()
    if framework == BOTTLE:
        return mk_bottle_service()
    return mk_aiohttp_service()


def mk_routes_and_openapi_specs(funcs, **configs):
    routes = []
    openapi_config = mk_config(
        'openapi', None, configs, default_configs, type=dict
    )
    openapi_spec = mk_openapi_template(openapi_config)
    header_inputs = mk_config('header_inputs', None, configs, default_configs)
    if header_inputs:
        openapi_spec['x-header-inputs'] = header_inputs
    for func in funcs:
        route, openapi_path = mk_route(func, **configs)
        routes.append(route)
        add_paths_to_spec(openapi_spec['paths'], openapi_path)
    openapi_filename = openapi_config.get('filename', None)
    if openapi_filename:
        with open(openapi_filename, 'w') as fp:
            json.dump(openapi_spec, fp)
    return routes, openapi_spec


def run_many_services(apps, run_now=False, **configs):
    framework = _get_framework(configs, default_configs)
    if framework == BOTTLE:
        return run_many_bottle_services(apps, run_now=run_now, **configs)
    return run_many_aiohttp_services(apps, run_now=run_now, **configs)


def run_many_bottle_services(apps, run_now=False, **configs):
    from bottle import Bottle, run

    parent_app = Bottle(catchall=False)
    for route, subapp in apps.items():
        parent_app.mount(route, subapp)
    if run_now:
        port = mk_config('port', None, configs, default_configs)
        run(parent_app, port=port)
    else:
        return parent_app


def run_many_aiohttp_services(apps, run_now=False, **configs):
    parent_app = web.Application()
    for route, subapp in apps.items():
        parent_app.add_subapp(route, subapp)
    if run_now:
        port = mk_config('port', None, configs, default_configs)
        web.run_app(parent_app, port=port)
    else:
        return parent_app


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


def _get_framework(configs, default_configs):
    framework = mk_config('framework', None, configs, default_configs)
    os.environ['PY2HTTP_FRAMEWORK'] = framework
    return framework
