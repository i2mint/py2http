from inspect import signature, Signature, Parameter
from typing import Any, _TypedDictMeta, T_co

complex_type_mapping = {}
json_types = [list, str, int, float, dict, bool]


def mk_sub_dict_schema_from_typed_dict(typed_dict):
    properties = {}
    for key, value in typed_dict.__annotations__.items():
        properties[key] = {'required': typed_dict.__total__}
        if getattr(value, '_name', None) == 'Iterable':
            properties[key]['type'] = list
            properties[key]['items'] = mk_sub_list_schema_from_iterable(value)
        elif value in json_types:
            properties[key]['type'] = value
        elif isinstance(value, _TypedDictMeta):
            properties[key]['type'] = 'object'
            properties[key]['properties'] = mk_sub_dict_schema_from_typed_dict(value)
        else:
            properties[key]['type'] = Any
    return properties


def mk_sub_list_schema_from_iterable(iterable_type):
    result = {}
    items_type = iterable_type.__args__[0]
    if type(items_type) == _TypedDictMeta:
        result['type'] = 'object'
        result['properties'] = mk_sub_dict_schema_from_typed_dict(items_type)
    elif getattr(items_type, '_name', None) == 'Iterable':
        result['type'] = list
        result['items'] = mk_sub_list_schema_from_iterable(items_type)
    elif items_type in json_types:
        result['type'] = items_type
    else:
        items_type = Any
    return result


# changes: simplified from sig.parameters[key] to looping over items of parameters
# changes: added include_func_params and handling
# changes: added docs and doctests
def mk_input_schema_from_func(func, exclude_keys=None, include_func_params=False):
    """Make the openAPI input schema for a function.

    :param func: A callable
    :param exclude_keys: keys to exclude in the schema
    :param include_func_params: Boolean indicating whether the python Parameter objects should
        also be included (under the field `x-py-param`)
    :return: An openAPI input schema dict

    >>> from py2http.schema_tools import mk_input_schema_from_func
    >>> import typing
    >>>
    >>> def add(a, b: float = 0.0) -> float:
    ...     '''Adds numbers'''
    ...     return a + b
    ...
    >>> got = mk_input_schema_from_func(add)
    >>> expected = {
    ...     'a': {'required': True, 'default': None, 'type': typing.Any},
    ...     'b': {'required': False, 'default': 0.0, 'type': float}}
    >>> assert got == expected, f"\\n  expected {expected}\\n  got {got}"
    >>>
    >>>
    >>> # TODO: Look into this one: it results in a x default=None (there should be no default)
    >>> #       and a type for y (there should be no type, unless by convention)
    >>> def mult(x: float, y=1, z: int=1):
    ...     return (x * y) ** z
    ...
    >>> got = mk_input_schema_from_func(mult)
    >>> expected = {
    ...     'x': {'required': True, 'default': None, 'type': float},
    ...     'y': {'required': False, 'default': 1, 'type': int},
    ...     'z': {'required': False, 'type': int, 'default': 1}
    ...     }
    >>> assert got == expected, f"\\n  expected {expected}\\n  got {got}"
    """
    if not exclude_keys:
        exclude_keys = {}
    input_schema = {}
    params = signature(func).parameters
    for key, param in params.items():
        if key in exclude_keys:
            continue

        default = None  # TODO: Not used. Check why
        default_type = Any
        p = {'required': True}
        if param.default != Signature.empty:
            default = param.default
            p['required'] = False
            if type(default) in json_types:
                default_type = type(default)  # TODO: perhaps you meant json_types[type(default)] ?
        p['default'] = default

        arg_type = default_type  # TODO: Not used. Check why (seems the if clause does covers all)
        if param.annotation != Signature.empty:
            arg_type = param.annotation
            if isinstance(arg_type, _TypedDictMeta):
                p['type'] = 'object'
                p['properties'] = mk_sub_dict_schema_from_typed_dict(arg_type)
                continue
            if getattr(arg_type, '_name', None) == 'Iterable':
                p['items'] = mk_sub_list_schema_from_iterable(arg_type)
                arg_type = list
            elif arg_type not in json_types and not complex_type_mapping.get(arg_type):
                arg_type = default_type
        else:
            arg_type = default_type  # TODO: Think. Could be a convention, but no applicable in all cases.
        p['type'] = arg_type

        if include_func_params:
            p['x-py-param'] = param
        # map key to this p info
        input_schema[key] = p
    return input_schema


def mk_output_schema_from_func(func):
    result = {}
    sig = signature(func)
    output_type = sig.return_annotation
    # print(f'output_type: {output_type}')  # TODO: Remove: Use conditional logging instead
    if output_type in [Signature.empty, Any]:
        return {}
    if isinstance(output_type, _TypedDictMeta):
        result['type'] = 'object'
        result['properties'] = mk_sub_dict_schema_from_typed_dict(output_type)
    elif getattr(output_type, '_name', None) == 'Iterable':
        result['type'] = list
        result['items'] = mk_sub_list_schema_from_iterable(output_type)
    elif output_type not in json_types and not complex_type_mapping.get(output_type):
        return {}
    else:
        result['type'] = output_type
    return result


# TODO write this function to take the output from
# mk_input_schema_from_func and create a validator function
# that takes an input_kwargs dict and makes sure the type of each value
# matches the schema
def mk_input_validator_from_schema(schema):
    def input_validator(input_kwargs):
        print('Your arguments are fallacious.')
        return False


# TODO write this function to take a dict like the following and create an input mapper
# (assume deserialization has already been taken care of)
#
# example_transform = {
#     'outer_to_outer': {
#         'output_key': 'outer1',
#         'type': str, # Python type is str, JSON type is string
#     },
#     'outer_to_inner': {
#         'output_key': 'inner1.value2',
#         'type': int, # Python type is int, JSON type is number
#     },
#     'container': {
#         'inner_to_inner': {
#             'output_key': 'inner1.value1',
#             'type': Iterable[Iterable[int]] # Complex type, will be mapped to a nested list in JSON schema for OpenAPI
#         },
#         'inner_to_outer': {
#             'output_key': 'outer2',
#             'type': np.array, # Python type is array, JSON type is list; requires custom handling
#         }
#     }
# }


def mk_input_mapper(transform):
    pass
    # def input_mapper(req_body):
    #     def map_value(output, key, transform_value):
    #         output_key = transform_value.get('output_key', None)
    #         if output_key:
    #             output[output_key] = get_nested_prop(req_body, output_key)
    #     result = {}
    #     for k, v in transform.items():
    #         map_value(result, k, v)
    #     return result
    # return handle_json(input_mapper)
