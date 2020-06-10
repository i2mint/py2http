from aiohttp import web
import inspect
import json
from warnings import warn

from py2http.default_configs import default_configs


def method_not_found(method_name):
    raise web.HTTPNotFound(text=json.dumps({'error': f'method {method_name} not found'}),
                           content_type='application/json')


def mk_config(key, func, funcname, configs, defaults, **options):
    result = getattr(func, key, configs.get(key, None))
    if result:
        if isinstance(result, dict) and funcname in result:
            result = result[funcname]
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
    return result


def mk_route(function, **configs):
    method_name = function.__name__
    input_mapper = mk_config('input_mapper', function, method_name, configs, default_configs)
    # TODO: perhaps collections.abc.Mapping instead of dict?
    assert callable(input_mapper), f'Invalid input mapper for function {method_name}, must be callable'

    input_validator = mk_config('input_validator', function, method_name, configs, default_configs)
    assert callable(input_validator), f'Invalid input validator for function {method_name}, must be callable'

    output_mapper = mk_config('output_mapper', function, method_name, configs, default_configs)
    assert callable(output_mapper), f'Invalid output mapper for function {method_name}, must be callable'

    async def handle_request(req):
        print('reached handle_request')
        input_tuple = input_mapper(req)
        if inspect.isawaitable(input_tuple):  # Pattern: pass-on async property
            input_tuple = await input_tuple
        input_args, input_kwargs = input_tuple
        print(input_args, input_kwargs)

        validation_result = input_validator(input_args, input_kwargs)
        if validation_result is not True:
            raise web.HTTPBadRequest(text=json.dumps({'error': validation_result}),
                                     content_type='application/json')

        raw_result = function(**input_kwargs)
        if inspect.isawaitable(raw_result):  # Pattern: pass-on async property
            raw_result = await raw_result
            print(f'awaited result, {raw_result}')
        else:
            print(f'sync result, {raw_result}')

        return output_mapper(raw_result)

    http_method = mk_config('http_method', function, method_name, configs, default_configs).lower()
    if http_method not in ['get', 'put', 'post', 'delete']:
        http_method = 'post'
    web_mk_route = getattr(web, http_method)
    route = mk_config('route', function, method_name, configs, default_configs)
    if not route:
        route = f'/{method_name}'
    return web_mk_route(route, handle_request)


def handle_ping():
    return web.json_response({'ping': 'pong'})


def run_http_service(functions, **configs):
    app = mk_http_service(functions, **configs)
    port = mk_config('port', None, None, configs, default_configs)
    web.run_app(app, port=port)


def mk_http_service(functions, **configs):
    middleware = mk_config('middleware', None, None, configs, default_configs)
    app = web.Application(middlewares=middleware)
    routes = [mk_route(item, **configs) for item in functions]
    app.add_routes([web.get('/ping', handle_ping), *routes])
    return app


def run_many_services(apps, **configs):
    app = web.Application()
    for route, subapp in apps.items():
        app.add_subapp(route, subapp)
    port = mk_config('port', None, None, configs, default_configs)
    web.run_app(app, port=port)
