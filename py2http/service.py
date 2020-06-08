from aiohttp import web
import inspect
import json
from warnings import warn

from py2http.default_configs import default_configs


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
        result = configs.get(defaults, None)
    return result


def handle_ping():
    return web.json_response({'ping': 'pong'})


def mk_request_handler(controller, **configs):

    def method_not_found(method_name):
        raise web.HTTPNotFound(text=json.dumps({'error': f'method {method_name} not found'}),
                               content_type='application/json')


    async def handle_request(req):

        # method
        method_name = req.match_info.get('method', '')
        if not method_name:
            if callable(controller):
                method = controller
            else:
                method_name = '*empty*'
                method_not_found(method_name)
        else:
            method = getattr(controller, method_name, None)
            if not method:
                method_not_found(method_name)

        assert callable(method), "method should be callable at this point"  # TODO: Handle more finely

        # input_mapper
        input_mapper = mk_config('input_mapper', configs, default_configs)
        if isinstance(input_mapper, dict) and method_name in input_mapper:
            input_mapper = input_mapper[method_name]
        if callable(input_mapper):
            if inspect.isawaitable(input_mapper):  # Pattern: pass-on async property
                input_kwargs = await input_mapper(req)
            else:
                input_kwargs = input_mapper(req)
        else:
            input_kwargs = {}

        # input_validator
        input_validator = mk_config('input_validator', configs, default_configs)
        if isinstance(input_validator, dict) and method_name in input_validator:
            input_validator = input_validator[method_name]
        if callable(input_validator):
            validation_result = input_validator(input_kwargs)
            if validation_result is not True:
                raise web.HTTPBadRequest(text=json.dumps({'error': validation_result}),
                                         content_type='application/json')

        # call the method
        if inspect.isawaitable(method):  # Pattern: pass-on async property
            raw_result = await method(**input_kwargs)
        else:
            raw_result = method(**input_kwargs)

        # output mapping
        output_mapper = mk_config('output_mapper', configs, default_configs)
        if isinstance(output_mapper, dict) and method_name in output_mapper:
            output_mapper = output_mapper[method_name]  # assumes the value is a callable
            assert callable(output_mapper), f"Should be a callable, was not: {output_mapper}"

        if callable(output_mapper):
            result = output_mapper(raw_result)
        else:
            result = raw_result
        return result
    return handle_request


def run_http_service(controller, **config):
    app = web.Application()
    request_handler = mk_request_handler(controller, **config)
    app.add_routes([web.get('/ping', handle_ping),
                    web.post('/{method}', request_handler)])
    web.run_app(app)
