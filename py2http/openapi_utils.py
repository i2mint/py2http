from typing import Any


def openapi_type_mapping(obj_type):
    if obj_type == str:
        return 'string'
    if obj_type == int:
        return 'number'
    if obj_type == float:
        return 'number'
    if obj_type == list:
        return 'array'
    if obj_type == dict:
        return 'object'
    if obj_type == bool:
        return 'boolean'
    if obj_type == Any:
        return '{}'
    return None


BINARY = 'binary'


def mk_openapi_template(config=None):
    if not config:
        config = {}
    return {
        'openapi': '3.0.2',
        'info': {
            'title': config.get('title', 'default'),
            'version': config.get('version', '0.1'),
        },
        'servers': [{'url': config.get('base_url', 'http://localhost:3030/')}],
        'paths': {},
    }


def add_paths_to_spec(paths_spec, new_paths):
    for pathname in new_paths.keys():
        for http_method in new_path[pathname].keys():
            if paths_spec.get(pathname, {}).get(http_method, None):
                raise ValueError(f'HTTP method {http_method} already exists for path {pathname}')
        paths_spec[pathname] = new_paths[pathname]


def mk_openapi_path(pathname,
                    method='post',
                    request_content_type='application/json',
                    request_dict=None,
                    response_content_type='application/json',
                    response_object=None,
                    path_fields=None):
    method = method.lower()
    if method not in ['get', 'put', 'post', 'delete']:
        raise ValueError('HTTP method must be GET, PUT, POST, DELETE (case-insensitive)')
    if not path_fields:
        path_fields = {}
    new_path = {pathname: {method: dict(path_fields)}}
    new_path_spec = new_path[pathname][method]
    if request_dict:
        content_type = request_content_type
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
                response_content_type: {}
            }
        }
    }
    if response_object:
        new_path_spec['responses']['200']['content'][request_content_type] = mk_obj_schema(response_object)
    return new_path_spec


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
        raise ValueError(f'Request schema value {key} contains an invalid type. Only JSON-compatible types are allowed.')
    if val_type == 'object':
        output = {'type': 'object', 'properties': mk_schema(request_dict)}
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
