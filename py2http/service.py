from aiohttp import web
import inspect
import json
from typing import Callable

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
    'input_validator': Callable,
    'output_mapper': Callable,
})


def mk_config(key, func, configs, defaults, **options):
    """
    Get a config value for a function. First checks the properties of the function,
    then the configs, then the defaults.

    :param key: The key to search for
    :param func: The function associated with the config
    :param configs: A config dict to search
    :param defaults: The default configs to fall back on
    :param **options: Additional options

    :Keyword Arguments:
        * *funcname*
          The name of the function, if not the same as func.__name__
        * *type*
          The expected type of the output (use Callable for functions)
    """
    funcname = options.get('funcname', getattr(func, '__name__', None))
    result = getattr(func, key, configs.get(key, None))
    if isinstance(result, dict):
        dict_value = result.get(funcname, None)
        if dict_value:
            result = dict_value
        elif options.get('type', None) is not dict:
            result = None
    if result:
        expected_type = options.get('type', None)
        if not expected_type:
            default_value = defaults.get(key, None)
            assert default_value is not None, f'Missing default value for key {key}'
            if callable(default_value):
                expected_type = Callable
            else:
                expected_type = type(default_value)
        assert isinstance(result, expected_type), f'Config {key} does not match type {expected_type}.'
    else:
        result = defaults.get(key, None)
    return result


from collections import namedtuple


# TODO: Just to try out a smoother interface. Delete if never used.

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


def mk_route(func, **configs):
    """
    Generate an aiohttp route object and an OpenAPI path specification for a function

    :param func: The function

    :Keyword Arguments: The configuration settings
    """
    # TODO: perhaps collections.abc.Mapping instead of dict?

    # 1: Replacement proposal
    input_mapper, input_validator, output_mapper, header_inputs = mk_config_nt(
        ['input_mapper', 'input_validator', 'output_mapper', 'header_inputs'],
        func, configs, default_configs)
    # input_mapper, input_validator, output_mapper, header_inputs = mk_configs(
    #     ['input_mapper', 'input_validator', 'output_mapper', 'header_inputs'],
    #     func, configs, default_configs
    # )
    # 1: To replace this   # TODO: Test and choose
    # input_mapper = mk_config('input_mapper', func, configs, default_configs)
    # input_validator = mk_config('input_validator', func, configs, default_configs)
    # output_mapper = mk_config('output_mapper', func, configs, default_configs)
    # header_inputs = mk_config('header_inputs', func, configs, default_configs)

    exclude_request_keys = header_inputs.keys()
    request_schema = getattr(input_mapper,
                             'request_schema',
                             mk_input_schema_from_func(func, exclude_keys=exclude_request_keys))
    response_schema = getattr(output_mapper,
                              'response_schema',
                              mk_output_schema_from_func(output_mapper))
    if not response_schema:
        response_schema = getattr(func,
                                  'response_schema',
                                  mk_output_schema_from_func(func))

    # TODO: Remove print (and implement conditional logging)
    print(f'response_schema: {response_schema}')

    async def handle_request(req):
        input_kwargs = input_mapper(req)
        if inspect.isawaitable(input_kwargs):  # Pattern: pass-on async property
            input_kwargs = await input_kwargs

        validation_result = input_validator(input_kwargs)
        if validation_result is not True:
            raise web.HTTPBadRequest(text=json.dumps({'error': validation_result}),
                                     content_type='application/json')

        raw_result = func(**input_kwargs)
        if inspect.isawaitable(raw_result):  # Pattern: pass-on async property
            raw_result = await raw_result

        final_result = output_mapper(raw_result, input_kwargs)
        if inspect.isawaitable(final_result):
            final_result = await final_result
        if not isinstance(final_result, web.Response):
            final_result = web.json_response(final_result)
        return final_result

    http_method = mk_config('http_method', func, configs, default_configs).lower()
    if http_method not in ['get', 'put', 'post', 'delete']:
        http_method = 'post'
    web_mk_route = getattr(web, http_method)

    method_name = mk_config('name', func, configs, default_configs)
    if not method_name:
        method_name = func.__name__

    path = mk_config('route', func, configs, default_configs)
    if not path:
        path = f'/{method_name}'
    route = web_mk_route(path, handle_request)
    openapi_path = mk_openapi_path(path, http_method,
                                   request_dict=request_schema,
                                   response_dict=response_schema,
                                   path_fields={'x-method_name': method_name})
    return route, openapi_path


def handle_ping(req):
    # the req param is required for this function to work as an aiohttp route
    # even though it's not used, so don't remove it
    return web.json_response({'ping': 'pong'})


def run_http_service(funcs, **configs):
    app = mk_http_service(funcs, **configs)
    port = mk_config('port', None, configs, default_configs)
    web.run_app(app, port=port)


def mk_http_service(funcs, **configs):
    middleware = mk_config('middleware', None, configs, default_configs)
    app = web.Application(middlewares=middleware)
    routes, openapi_spec = mk_routes_and_openapi_specs(funcs, configs)
    app.add_routes([web.get('/ping', handle_ping), *routes])
    app.openapi_spec = openapi_spec
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
