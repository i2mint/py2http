from typing import Any

from py2http.default_configs import DFLT_CONTENT_TYPE
from py2http.util import conditional_logger, CreateProcess, lazyprop

oatype_for_pytype = {
    str: 'string',
    int: 'integer',
    float: 'number',
    list: 'array',
    dict: 'object',
    bool: 'boolean',
    Any: '{}',
}


def openapi_type_mapping(obj_type):
    if isinstance(obj_type, str):
        return obj_type
    else:
        return oatype_for_pytype.get(obj_type, None)


BINARY = 'binary'
DFLT_SERVER_URL = 'http://localhost:3030'


class OpenApiExtractor:
    def __init__(self, openapi_spec, func_to_path=None):
        self.openapi_spec = openapi_spec
        if func_to_path is None:

            def func_to_path(
                func,
            ):  # TODO: Fragile. Need to make func <-> path more robust (e.g. include in openapi_spec)
                return '/' + func.__name__

        self.func_to_path = func_to_path

    def paths_and_methods_items(self):
        for path, path_info in self.openapi_spec['paths'].items():
            for method, path_method_info in path_info.items():
                yield (path, method), path_method_info

    @lazyprop
    def info_for_path_and_method(self):
        return dict(self.paths_and_methods_items())

    def func_and_info(self, *funcs):
        for func in funcs:
            pass


def mk_openapi_template(config=None):
    if not config:
        config = {}
    openapi_spec = {
        'openapi': '3.0.2',
        'info': {
            'title': config.get('title', 'default'),
            'version': config.get('version', '0.1'),
        },
        'servers': [{'url': config.get('base_url', DFLT_SERVER_URL)}],
        'paths': {},
    }
    auth_config = config.get('auth', None)
    if auth_config:
        auth_type = auth_config.get('auth_type', 'jwt')
        login_details = auth_config.get('login_details', None)
        set_auth(openapi_spec, auth_type, login_details=login_details)
    return openapi_spec


def add_paths_to_spec(paths_spec, new_paths):
    for pathname in new_paths.keys():
        for http_method in new_paths[pathname].keys():
            if paths_spec.get(pathname, {}).get(http_method, None):
                raise ValueError(
                    f'HTTP method {http_method} already exists for path {pathname}'
                )
        paths_spec[pathname] = new_paths[pathname]


def set_auth(openapi_spec, auth_type='jwt', *, login_details=None):
    """
    :param openapi_spec: An OpenAPI formatted server specification
    :param auth_type: Either 'jwt' or 'api_key'
    :param login_details: Optional - {
        'login_url': the login url
        'refresh_url': the refresh url, if applicable
        'login_inputs': a list of strings e.g. ['account', 'email', 'password']
        'refresh_inputs': a list of strings e.g. ['account', 'refresh_token']
        'outputs': a list of strings e.g. ['jwt', 'refresh_token']
    }
    ""

    """
    if auth_type not in ['jwt', 'api_key']:
        raise ValueError("auth_type must be either 'jwt' or 'api_key'")
    if not login_details:
        login_details = {}
    if not openapi_spec.get('components'):
        openapi_spec['components'] = {}
    if not openapi_spec['components'].get('securitySchemes'):
        openapi_spec['components']['securitySchemes'] = {}
    if not openapi_spec.get('security'):
        openapi_spec['security'] = {}
    if auth_type == 'jwt':
        openapi_spec['components']['securitySchemes']['bearerAuth'] = {
            'type': 'http',
            'scheme': 'bearer',
            'bearerFormat': 'JWT',
        }
        if login_details:
            openapi_spec['components']['securitySchemes']['bearerAuth'][
                'x-login'
            ] = login_details
        openapi_spec['security']['bearerAuth'] = []
    else:
        openapi_spec['components']['securitySchemes']['apiKeyAuth'] = {
            'type': 'apiKey',
            'in': 'header',
            'name': 'Authorization',
        }
        openapi_spec['security']['apiKey'] = []


def mk_openapi_path(
    pathname='/',
    method='post',
    request_content_type=DFLT_CONTENT_TYPE,
    request_schema=None,
    response_content_type=DFLT_CONTENT_TYPE,
    response_schema=None,
    path_fields=None,
):
    # TODO: correctly handle input args in URL (params and query)
    # TODO: allow args in header (specific to path, not just for whole service)
    method = method.lower()
    if method not in ['get', 'put', 'post', 'delete']:
        raise ValueError(
            'HTTP method must be GET, PUT, POST, or DELETE (case-insensitive)'
        )
    if not path_fields:
        path_fields = {}
    new_path = {pathname: {method: dict(path_fields)}}
    new_path_spec = new_path[pathname][method]
    if request_schema:
        new_path_spec['requestBody'] = {
            'required': True,
            'content': {
                request_content_type: {'schema': mk_arg_schema(request_schema)}
            },
        }
    new_path_spec['responses'] = {
        '200': {'description': '', 'content': {response_content_type: {'schema': {}}}}
    }
    if response_schema:
        new_path_spec['responses']['200']['content'][response_content_type][
            'schema'
        ] = mk_arg_schema(response_schema)
    return new_path


def mk_obj_schema(request_object):
    output = {}
    try:
        for key, item in request_object.items():
            output[key] = mk_arg_schema(item)
    except AttributeError:
        print(f'Accidentally got a tuple: {str(request_object)}')
    return output


def mk_arg_schema(arg):
    arg_type = arg.get('type', Any)
    required = True
    if 'default' in arg:
        required = False
        default = arg['default']
    val_type = openapi_type_mapping(arg.get('type', Any))
    if not val_type:
        raise ValueError(
            f'Request schema value {arg_type} is an invalid type. Only JSON-compatible types are allowed.'
        )
    if val_type == 'object':
        output = {
            'type': 'object',
            'properties': mk_obj_schema(arg.get('properties', {})),
        }
        required_props = arg.get('required', [])
        if required_props:
            output['required'] = required_props
    elif val_type == 'array':
        output = {'type': 'array'}
        sub_args = arg.get('items', None)
        if sub_args:
            output['items'] = mk_arg_schema(sub_args)
    elif val_type == 'number':
        output = {'type': val_type, 'format': 'float'}
    elif arg_type == BINARY:
        output = {'type': 'string', 'format': 'binary'}
    else:
        output = {'type': val_type}
    if not required:
        output['default'] = default
    return output


from py2http.schema_tools import mk_input_schema_from_func


def func_to_openapi_spec(
    func,
    exclude_keys=None,
    pathname=None,
    method='post',
    request_content_type=DFLT_CONTENT_TYPE,
    #                     request_dict=None,
    response_content_type=DFLT_CONTENT_TYPE,
    response_schema=None,
    path_fields=None,
):
    pathname = (
        pathname or func.__name__
    )  # TODO: need safer get_name func, and name collision management
    request_schema = mk_input_schema_from_func(func, exclude_keys)
    return mk_openapi_path(
        pathname,
        method=method,
        request_content_type=request_content_type,
        request_schema=request_schema,
        response_content_type=response_content_type,
        response_schema=response_schema,
        path_fields=path_fields,
    )


# Wish for sigfrom and/or mkwith decorators to be able to do func_to_openapi_spec like this:
#
# @sigfrom(mk_input_schema_from_func, mk_openapi_path, exclude='request_dict', dflts={'pathname': None})
# def func_to_openapi_spec(*args, **kwargs):
#     kws1, kws2 = extract_kwargs(mk_input_schema_from_func, mk_openapi_path)
#     kws1['pathname'] = kws1['pathname'] or kws1['func'].__name__
#     request_dict = mk_input_schema_from_func(**kws1)
#     return mk_openapi_path(request_dict=request_dict, **kws2)
#
# @sigfrom(mk_input_schema_from_func, mk_openapi_path, exclude='request_dict', dflts={'pathname': None})
# def func_to_openapi_spec(*args, **kwargs):
#     pathname = pathname or func.__name__
#     request_dict = mk_input_schema_from_func(func, exclude_keys)
#     return mk_openapi_path(request_dict=request_dict, **kws2)


# TODO: What's below is meant for http2py, and lives/maintains there.
#   Copied below (but commented out) for reference. Can delete if never used.
# from inspect import Parameter, Signature
#
# PK = Parameter.POSITIONAL_OR_KEYWORD
#
#
# def _params_from_props(openapi_props):
#     for name, p in openapi_props.items():
#         yield Parameter(name=name, kind=PK,
#                         default=p.get('default', Parameter.empty),
#                         annotation=p.get('type', Parameter.empty))
#
#
# def add_annots_from_openapi_props(func, openapi_props):
#     func.__signature__ = Signature(_params_from_props(openapi_props))
#     return func
#

# TODO Where to document the format of header inputs to be consumed by http2py
# configs = {
#     'header_inputs': {
#         'account': {
#             'header': 'Authorization',
#             'type': 'string',
#             'encoding': 'jwt',
#         },
#         'email': {
#             'header': 'Authorization',
#             'type': 'string',
#             'encoding': 'jwt',
#         },
#         'api_key': {
#             'header': 'x-api-key',
#             'type': 'string', # no encoding, defaults to raw
#         }
#     }
# }
