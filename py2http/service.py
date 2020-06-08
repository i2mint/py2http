from aiohttp import web
import inspect
import json
from warnings import warn

from py2http.default_configs import default_configs


def method_not_found(method_name):
    raise web.HTTPNotFound(text=json.dumps({'error': f'method {method_name} not found'}),
                           content_type='application/json')


def mk_config(key, configs, defaults, **options):
    result = configs.get(key, None)
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
    return result


def mk_route(function, **configs):
    method_name = function.__name__
    input_mapper = getattr(function, 'input_mapper', None)
    if not input_mapper:
        input_mapper = mk_config('input_mapper', configs, default_configs)
        if isinstance(input_mapper, dict) and method_name in input_mapper:
            input_mapper = input_mapper[method_name]
    assert callable(input_mapper), f'Invalid input mapper for function {method_name}, must be callable'

    input_validator = getattr(function, 'input_validator', None)
    if not input_validator:
        input_validator = mk_config('input_validator', configs, default_configs)
        if isinstance(input_validator, dict) and method_name in input_validator:
            input_validator = input_validator[method_name]
    assert callable(input_validator), f'Invalid input validator for function {method_name}, must be callable'

    output_mapper = getattr(function, 'output_mapper', None)
    if not output_mapper:
        output_mapper = mk_config('output_mapper', configs, default_configs)
        if isinstance(output_mapper, dict) and method_name in output_mapper:
            output_mapper = output_mapper[method_name]
    assert callable(output_mapper), f'Invalid output mapper for function {method_name}, must be callable'

    async def handle_request(req):
        input_kwargs = input_mapper(req)
        if inspect.isawaitable(input_kwargs):  # Pattern: pass-on async property
            input_kwargs = await input_kwargs

        validation_result = input_validator(input_kwargs)
        if validation_result is not True:
            raise web.HTTPBadRequest(text=json.dumps({'error': validation_result}),
                                     content_type='application/json')

        raw_result = function(**input_kwargs)
        if inspect.isawaitable(raw_result):  # Pattern: pass-on async property
            raw_result = await raw_result

        return output_mapper(raw_result)

    return web.post(f'/{method_name}', handle_request)


def handle_ping():
    return web.json_response({'ping': 'pong'})


def run_http_service(functions, **configs):
    app = web.Application()
    routes = [mk_route(item, **configs) for item in functions]
    app.add_routes([web.get('/ping', handle_ping), *routes])
    web.run_app(app, port=3030)
