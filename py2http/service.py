from aiohttp import web
import inspect
import json
from warnings import warn

from py2http.default_configs import default_configs
from py2http.openapi_utils import add_paths_to_spec, mk_openapi_path, mk_openapi_template
from py2http.schema_tools import mk_input_schema_from_func


def method_not_found(method_name):
    raise web.HTTPNotFound(text=json.dumps({'error': f'method {method_name} not found'}),
                           content_type='application/json')


def mk_config(key, func, funcname, configs, defaults, **options):
    result = getattr(func, key, configs.get(key, None))
    if isinstance(result, dict):
        result = result.get(funcname, None)
    if result:
        if options.get('is_func', None) and not callable(result):
            warn(f'Config {key} is not callable, using default.')
            result = defaults.get(key, None)
        else:
            expected_type = options.get('type', None)
            if expected_type and not isinstance(result, expected_type):
                warn(f'Config {key} does not match type {expected_type}, using default.')
                result = defaults.get(key, None)
    else:
        result = defaults.get(key, None)
    assert callable(result), f'Invalid input mapper for function {key}, must be callable'
    return result


def mk_route(function, **configs):
    method_name = function.__name__
    # TODO: perhaps collections.abc.Mapping instead of dict?
    input_mapper = mk_config('input_mapper', function, method_name, configs, default_configs)
    input_validator = mk_config('input_validator', function, method_name, configs, default_configs)
    output_mapper = mk_config('output_mapper', function, method_name, configs, default_configs)
    request_schema = getattr(input_mapper, 'request_schema', mk_input_schema_from_func(function))
    response_schema = getattr(output_mapper, 'response_schema', {})

    async def handle_request(req):
        print('reached handle_request')  # TODO: Debug prints. Should control.
        input_tuple = input_mapper(req)
        if inspect.isawaitable(input_tuple):  # Pattern: pass-on async property
            input_tuple = await input_tuple
        input_args, input_kwargs = input_tuple
        print(input_args, input_kwargs)  # TODO: Debug prints. Should control.

        validation_result = input_validator(input_args, input_kwargs)
        if validation_result is not True:
            raise web.HTTPBadRequest(text=json.dumps({'error': validation_result}),
                                     content_type='application/json')

        raw_result = function(**input_kwargs)
        if inspect.isawaitable(raw_result):  # Pattern: pass-on async property
            raw_result = await raw_result
            print(f'awaited result, {raw_result}')  # TODO: Debug prints. Should control.
        else:
            print(f'sync result, {raw_result}')  # TODO: Debug prints. Should control.

        final_result = output_mapper(raw_result, input_args, input_kwargs)
        if inspect.isawaitable(final_result):
            final_result = await final_result
        if not isinstance(final_result, web.Response):
            print('making it a response')
            final_result = web.json_response(final_result)
        else:
            print('correctly identified response type')
        print(f'final result: {type(final_result)}')
        return final_result

    http_method = mk_config('http_method', function, method_name, configs, default_configs).lower()
    if http_method not in ['get', 'put', 'post', 'delete']:
        http_method = 'post'
    web_mk_route = getattr(web, http_method)
    path = mk_config('route', function, method_name, configs, default_configs)
    if not path:
        path = f'/{method_name}'
    route = web_mk_route(path, handle_request)
    openapi_path = mk_openapi_path(path, http_method, request_dict=request_spec, response_dict=response_spec)
    return route, openapi_path


def handle_ping():
    return web.json_response({'ping': 'pong'})


def run_http_service(functions, **configs):
    app = mk_http_service(functions, **configs)
    port = mk_config('port', None, None, configs, default_configs)
    web.run_app(app, port=port)


def mk_http_service(functions, **configs):
    middleware = mk_config('middleware', None, None, configs, default_configs)
    app = web.Application(middlewares=middleware)
    routes = []
    openapi_config = configs.get('openapi', {})
    openapi_spec = mk_openapi_template(openapi_config)
    for item in functions:
        route, openapi_path = mk_route(item, **configs)
        routes.append(route)
        add_paths_to_spec(openapi_spec['paths'], openapi_path)

    openapi_filename = openapi_config.get('filename', None)
    if openapi_filename:
        with open(openapi_filename, 'w') as fp:
            json.dump(openapi_spec, fp)

    app.add_routes([web.get('/ping', handle_ping), *routes])
    return app


def run_many_services(apps, **configs):
    app = web.Application()
    for route, subapp in apps.items():
        app.add_subapp(route, subapp)
    port = mk_config('port', None, None, configs, default_configs)
    web.run_app(app, port=port)
