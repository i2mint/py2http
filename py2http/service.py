from aiohttp import web
import asyncio
from collections import namedtuple
from copy import deepcopy
from functools import partial
from inspect import isawaitable
import json
from typing import Any, Callable, Dict, Iterable, Optional, TypedDict, Union
from types import FunctionType
import logging
import os
from bottle import Bottle, run as run_bottle
import traceback
from swagger_ui import api_doc

from i2.errors import InputError, DataError, AuthorizationError
from i2 import Sig

from py2http.bottle_plugins import CorsPlugin, OPTIONS
from py2http.config import mk_config, FLASK, AIOHTTP, BOTTLE
from py2http.default_configs import (
    default_configs,
    DFLT_CONTENT_TYPE,
    default_input_mapper,
)
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
from py2http.constants import JSON_CONTENT_TYPE


def method_not_found(method_name):
    raise web.HTTPNotFound(
        text=json.dumps({'error': f'method {method_name} not found'}),
        content_type=JSON_CONTENT_TYPE,
    )


# default TypeAsserter used in this project
assert_type = TypeAsserter(
    types_for_kind={
        'input_mapper': Callable,
        'output_mapper': Callable,
    }
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
    Generate a route object and an OpenAPI path specification for a function

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
    if request_schema is None or input_mapper.__name__ == default_input_mapper.__name__:
        request_schema = mk_input_schema_from_func(
            func, exclude_keys=exclude_request_keys
        )
    request_content_type = getattr(input_mapper, 'content_type', DFLT_CONTENT_TYPE)
    response_schema = getattr(
        output_mapper,
        'response_schema',
        mk_output_schema_from_func(output_mapper),
    )
    if not response_schema:
        response_schema = getattr(
            func, 'response_schema', mk_output_schema_from_func(func)
        )
    response_content_type = getattr(output_mapper, 'content_type', DFLT_CONTENT_TYPE)

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
                    logger.log(level, traceback.format_exc(), exc_info=exc_info)
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
        inputs = input_mapper(req)
        input_args, input_kwargs = get_input_args_and_kwargs(inputs)
        raw_result = func(*input_args, **input_kwargs)
        return output_mapper(raw_result, **inputs)

    @handle_error
    async def aiohttp_handle_request(req):
        inputs = input_mapper(req)
        if isawaitable(inputs):  # Pattern: pass-on async property
            inputs = await inputs
        input_args, input_kwargs = get_input_args_and_kwargs(inputs)
        raw_result = func(*input_args, **input_kwargs)
        if isawaitable(raw_result):  # Pattern: pass-on async property
            raw_result = await raw_result
        final_result = output_mapper(raw_result, **inputs)
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

    extra_path_info = {'description': func.__doc__ or ''}
    path_fields = dict({'x-method_name': method_name}, **extra_path_info)
    openapi_path = mk_openapi_path(
        path,
        http_method,
        request_schema=request_schema,
        request_content_type=request_content_type,
        response_schema=response_schema,
        response_content_type=response_content_type,
        path_fields=path_fields,
    )

    return route, openapi_path


def mk_routes_and_openapi_specs(funcs, **configs):
    routes = []
    get_config = partial(
        mk_config, func=None, configs=configs, defaults=default_configs
    )
    openapi_config = get_config('openapi', type=dict)
    if 'base_url' not in openapi_config:
        host = get_config('host')
        port = get_config('port')
        protocol = 'https' if port == 443 else 'http'
        openapi_config['base_url'] = f'{protocol}://{host}:{port}'
    openapi_spec = mk_openapi_template(openapi_config)
    header_inputs = get_config('header_inputs')
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


Handlers = Iterable[
    Union[
        Callable,
        TypedDict(
            'HandlerWithMappers',
            endpoint=Callable,
            input_mapper=Optional[Callable],
            output_mapper=Optional[Callable],
        ),
    ]
]
SubAppSpec = TypedDict(
    'SubAppSpec',
    handlers=Handlers,
    config=Dict[str, Any],
)
AppSpec = Union[Handlers, Dict[str, Union[Handlers, SubAppSpec]]]


def mk_flask_app(funcs, **configs):
    from flask import Flask

    routes, openapi_spec = mk_routes_and_openapi_specs(funcs, **configs)
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
    app.add_url_rule('/ping', 'ping', lambda: {'ping': 'pong'})
    app.add_url_rule('/openapi', 'openapi', lambda: openapi_spec)
    app.openapi_spec = openapi_spec
    return app


def mk_bottle_app(funcs, **configs):
    from bottle import Bottle

    routes, openapi_spec = mk_routes_and_openapi_specs(funcs, **configs)
    app = Bottle(catchall=False)
    enable_cors = mk_config('enable_cors', None, configs, default_configs)
    plugins = mk_config('plugins', None, configs, default_configs)
    if enable_cors:
        cors_allowed_origins = mk_config(
            'cors_allowed_origins', None, configs, default_configs
        )
        app.install(CorsPlugin(cors_allowed_origins))
    publish_openapi = mk_config('publish_openapi', None, configs, default_configs)
    openapi_insecure = mk_config('openapi_insecure', None, configs, default_configs)
    publish_swagger = mk_config('publish_swagger', None, configs, default_configs)
    if plugins:
        for plugin in plugins:
            app.install(plugin)
    for route in routes:
        route_http_method = route.http_method.upper()
        http_methods = (
            route.http_method if not enable_cors else [OPTIONS, route_http_method]
        )
        # print(f'Mounting route: {route.path} {route.http_method.upper()}')
        app.route(route.path, http_methods, route, route.method_name)
    app.route(
        path='/ping', callback=lambda: {'ping': 'pong'}, name='ping', skip=plugins
    )
    if publish_openapi:
        skip = plugins if openapi_insecure else None
        app.route(
            path='/openapi',
            callback=lambda: openapi_spec,
            name='openapi',
            skip=skip,
        )
    app.openapi_spec = openapi_spec
    if publish_swagger:
        swagger_url = mk_config('swagger_url', None, configs, default_configs)
        swagger_title = mk_config('swagger_title', None, configs, default_configs)
        api_doc(
            app,
            config_spec=json.dumps(openapi_spec),
            url_prefix=swagger_url,
            title=swagger_title,
        )
    return app


def mk_aiohttp_app(funcs, **configs):
    routes, openapi_spec = mk_routes_and_openapi_specs(funcs, **configs)
    middleware = mk_config('middleware', None, configs, default_configs)
    app = web.Application(middlewares=middleware)
    app.add_routes(
        [
            web.get('/ping', lambda: web.json_response({'ping': 'pong'}), name='ping'),
            web.get(
                '/openapi', lambda: web.json_response(openapi_spec), name='openapi'
            ),
            *routes,
        ]
    )
    # adding a few more attributes
    app.openapi_spec = openapi_spec
    return app


@Sig.add_optional_keywords(default_configs)
def mk_app(app_spec: AppSpec, **configs):
    """
    Generates an application which exposes web services created from the given python
    functions to remotely run them.
    You can generate a multi-service application defining a route per API or sub
    application.

    First define a bunch of functions (or handlers) you want to expose as a web service.
    >>> def foo():
    ...     return 0
    ...
    >>> def bar():
    ...     return True
    ...

    Let's make a single-service application. A single API will be generated with an
    endpoint per handler, plus an auto-generated enpoints to ping the API.
    >>> handlers = [foo, bar]
    >>> app = mk_app(handlers)
    >>> app.get_url('bar')
    '/bar'
    >>> app.get_url('foo')
    '/foo'
    >>> app.get_url('ping')
    '/ping'

    You can also automatically generate an endpoint to expose the openapi specification
    of your API by activating the flag "publish_openapi". Publishing the openapi
    specification will allow a client application to use the specification object to
    build an interface to actually consume the API by wrapping the http layer.
    >>> app = mk_app(handlers, publish_openapi=True)
    >>> app.openapi_spec # doctest: +NORMALIZE_WHITESPACE
    {'openapi': '3.0.2', 'info': {'title': 'default', 'version': '0.1'}, 'servers':
    [{'url': 'http://localhost:3030'}], 'paths': {'/foo': {'post': {'x-method_name':
    'foo', 'description': '', 'requestBody': {'required': True, 'content':
    {'application/json': {'schema': {'type': 'object', 'properties': {}}}}},
    'responses': {'200': {'description': '', 'content': {'application/json':
    {'schema': {}}}}}}}, '/bar': {'post': {'x-method_name': 'bar', 'description': '',
    'requestBody': {'required': True, 'content': {'application/json': {'schema':
    {'type': 'object', 'properties': {}}}}}, 'responses': {'200': {'description': '',
    'content': {'application/json': {'schema': {}}}}}}}}}
    >>> app.get_url('openapi')
    '/openapi'

    Let's use http2py to consume the openapi specification
    >>> from http2py import HttpClient
    >>> api = HttpClient(openapi_spec=app.openapi_spec)
    >>> assert(hasattr(api, 'foo'))
    >>> assert(hasattr(api, 'bar'))

    Now, let's make a multi-service application. You only have to define a route per
    API with a list of handlers for each API.
    >>> handler_spec = {
    ...     'foo_api': [foo],
    ...     'bar_api': [bar],
    ... }
    >>> app = mk_app(handler_spec, publish_openapi=True)
    >>> app.get_url('/foo_api')
    '/foo_api'
    >>> app.get_url('/bar_api')
    '/bar_api'

    :param handler_spec: The handler specification. Can be a list of python to expose,
    or a dict with a list of functions to expose per route in case of a multi-service
    application.
    :type handler_spec: HandlerSpec
    :param **configs: The configuration for the application. See config.yaml for
    configuration documentation.
    :type **configs: dict
    """

    def mk_single_api_app():
        def add_mappers_to_config():
            handlers_with_mappers = [x for x in app_spec if isinstance(x, dict)]
            input_mappers = {}
            output_mappers = {}
            for handler in handlers_with_mappers:
                endpoint = handler['endpoint']
                input_mapper = handler.get('input_mapper')
                if input_mapper:
                    input_mappers[endpoint.__name__] = input_mapper
                output_mapper = handler.get('output_mapper')
                if output_mapper:
                    output_mappers[endpoint.__name__] = output_mapper
            if input_mappers:
                app_configs['input_mapper'] = input_mappers
            if output_mappers:
                app_configs['output_mapper'] = output_mappers

        app_configs = dict(configs)
        handlers = [x['endpoint'] if isinstance(x, dict) else x for x in app_spec]
        add_mappers_to_config()
        if framework == FLASK:
            return mk_flask_app(handlers, **app_configs)
        if framework == BOTTLE:
            return mk_bottle_app(handlers, **app_configs)
        return mk_aiohttp_app(handlers, **app_configs)

    def mk_multi_api_app():
        def get_web_framework_objects():
            if framework == BOTTLE:
                app = Bottle(catchall=False)
                return app, app.mount
            elif framework == AIOHTTP:
                app = web.Application()
                return app, app.add_subapp
            return None

        parent_app, add_subapp_meth = get_web_framework_objects()
        for route, route_spec in app_spec.items():
            if isinstance(route_spec, dict):
                handlers = route_spec['handlers']
                subapp_configs = route_spec['config']
            else:
                handlers = route_spec
                subapp_configs = deepcopy(configs)
            if 'openapi' not in subapp_configs:
                subapp_configs['openapi'] = {}
            if 'base_url' not in subapp_configs['openapi']:
                get_config = partial(
                    mk_config, func=None, configs=configs, defaults=default_configs
                )
                host = get_config('host')
                port = get_config('port')
                protocol = 'https' if port == 443 else 'http'
                subapp_configs['openapi']['base_url'] = f'{protocol}://{host}:{port}'
            subapp_configs['openapi']['base_url'] = (
                subapp_configs['openapi']['base_url'] + route
            )
            subapp = mk_app(handlers, **subapp_configs)
            add_subapp_meth(route, subapp)
        return parent_app

    framework = _get_framework(configs, default_configs)
    if isinstance(app_spec, dict):
        return mk_multi_api_app()
    return mk_single_api_app()


@Sig.add_optional_keywords(default_configs)
def run_app(app_obj: Union[AppSpec, Any], **configs):
    """
    Run an application which exposes web services created from the given python
    functions to remotely run them.
    You can generate a multi-service application defining a route per api or sub
    application.
    You can also generate the application first, then run it using this function.

    :param app_obj: The handler specification or application object. Can be a list of
    python to expose, or a dict with a list of functions to expose per route in case
    of a multi-service. Can also be a pre-generated application object to run.
    :type handler_spec: Union[HandlerSpec, Any]
    :param **configs: The configuration for the application. See
    `py2http.default_configs:default_configs` for defaults and config.yaml for
    configuration documentation.
    :type **configs: dict
    """

    def get_run_func():
        framework = _get_framework(configs, default_configs)
        if framework == BOTTLE:
            return run_bottle
        elif framework == AIOHTTP:
            return web.run_app
        raise NotImplementedError('')

    if isinstance(app_obj, Iterable):
        app = mk_app(app_obj, **configs)
        run_app(app, **configs)
    else:
        run_func = get_run_func()
        get_config = partial(
            mk_config, func=None, configs=configs, defaults=default_configs
        )
        host = get_config('host')
        port = get_config('port')
        server = get_config('server')
        ssl_certfile = get_config('ssl_certfile')
        ssl_keyfile = get_config('ssl_keyfile')

        # run_func(app_obj, host=host, port=port, ssl_context=ssl_context, server='gunicorn')
        run_func(
            app_obj,
            host=host,
            port=port,
            server=server,
            certfile=ssl_certfile,
            keyfile=ssl_keyfile,
        )


def _get_framework(configs, default_configs):
    framework = mk_config('framework', None, configs, default_configs)
    # NOTE Only support Bottle until we redesign py2http using a reusable tool for routing
    # if framework not in (FLASK, BOTTLE, AIOHTTP):
    if framework != BOTTLE:
        raise NotImplementedError(
            f'The Web Framework "{framework}" is not supported by py2http'
        )
    os.environ['PY2HTTP_FRAMEWORK'] = framework
    return framework
