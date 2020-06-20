from typing import Any

from glom import glom

oatype_for_pytype = {
    str: 'string', int: 'number', float: 'number', list: 'array', dict: 'object', bool: 'boolean', Any: '{}'
}


def openapi_type_mapping(obj_type):
    if isinstance(obj_type, str):
        return obj_type
    else:
        return oatype_for_pytype.get(obj_type, None)


BINARY = 'binary'


def mk_openapi_template(config=None):
    if not config:
        config = {}
    openapi_spec = {
        'openapi': '3.0.2',
        'info': {
            'title': config.get('title', 'default'),
            'version': config.get('version', '0.1'),
        },
        'servers': [{'url': config.get('base_url', 'http://localhost:3030/')}],
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
                raise ValueError(f'HTTP method {http_method} already exists for path {pathname}')
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
        raise ValueError('auth_type must be either \'jwt\' or \'api_key\'')
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
            openapi_spec['components']['securitySchemes']['bearerAuth']['x-login'] = login_details
        openapi_spec['security']['bearerAuth'] = []
    else:
        openapi_spec['components']['securitySchemes']['apiKeyAuth'] = {
            'type': 'apiKey',
            'in': 'header',
            'name': 'Authorization',
        }
        openapi_spec['security']['apiKey'] = []


def mk_openapi_path(pathname='/',
                    method='post',
                    request_content_type='application/json',
                    request_dict=None,
                    response_content_type='application/json',
                    response_dict=None,
                    path_fields=None):
    # TODO: correctly handle input args in URL (params and query)
    # TODO: allow args in header (specific to path, not just for whole service)
    method = method.lower()
    if method not in ['get', 'put', 'post', 'delete']:
        raise ValueError('HTTP method must be GET, PUT, POST, or DELETE (case-insensitive)')
    if not path_fields:
        path_fields = {}
    new_path = {pathname: {method: dict(path_fields)}}
    new_path_spec = new_path[pathname][method]
    if request_dict:
        new_path_spec['requestBody'] = {
            'required': True,
            'content': {
                request_content_type: {
                    'schema': {
                        'type': 'object',
                        'properties': mk_obj_schema(request_dict),
                    }
                }
            }
        }
    new_path_spec['responses'] = {
        '200': {
            'content': {
                response_content_type: {
                    'schema': {}
                }
            }
        }
    }
    if response_dict:
        new_path_spec['responses']['200']['content'][request_content_type]['schema'] = mk_arg_schema(response_dict)
    return new_path


def mk_obj_schema(request_object):
    output = {}
    for key, item in request_object.items():
        output[key] = mk_arg_schema(item)
    return output


def mk_arg_schema(arg):
    output = {}
    arg_type = arg.get('type', Any)
    val_type = openapi_type_mapping(arg.get('type', Any))
    if not val_type:
        raise ValueError(f'Request schema value {arg_type} is an invalid type. Only JSON-compatible types are allowed.')
    if val_type == 'object':
        output = {'type': 'object', 'properties': mk_obj_schema(arg.get('properties', {}))}
    elif val_type == 'array':
        output = {'type': 'array'}
        sub_args = arg.get('items', None)
        if sub_args:
            output['items'] = mk_arg_schema(sub_args)
    elif arg_type == BINARY:
        output = {'type': 'string', 'format': 'binary'}
    else:
        output = {'type': val_type}
    return output


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