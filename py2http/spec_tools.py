from inspect import signature, Signature
from typing import Any, Iterable, _TypedDictMeta, T_co

complex_type_mapping = {}
json_types = [list, str, int, float, dict, bool]


def mk_sub_dict_spec_from_typed_dict(typed_dict):
    properties = {}
    for key, value in typed_dict.__annotations__:
        properties[key] = {'required': typed_dict.__total__}
        if getattr(value, '_name', None) == 'Iterable':
            properties[key]['type'] = list
            properties[key]['items'] = mk_sub_list_spec_from_iterable(value)
        elif value in json_types:
            properties[key]['type'] = value
        elif type(value) == _TypedDictMeta:
            properties[key]['type'] = 'object'
            properties[key]['properties'] = mk_sub_dict_spec_from_typed_dict(value)
        else:
            properties[key]['type'] = Any
    return properties


def mk_sub_list_spec_from_iterable(iterable_type):
    result = {}
    items_type = iterable_type.__args__[0]
    if type(items_type) == _TypedDictMeta:
        result['type'] = 'object'
        result['properties'] = mk_sub_dict_spec_from_typed_dict(items_type)
    elif getattr(items_type, '_name', None) == 'Iterable':
        result['type'] = list
        result['items'] = mk_sub_list_spec_from_iterable(items_type)
    elif items_type in json_types:
        result['type'] = items_type
    else:
        items_type = Any
    return result


def mk_input_spec_from_func(func):
    result = {}
    sig = signature(func)
    for key in sig.parameters:
        default = None
        default_type = Any
        result[key] = {'required': True}
        if sig.parameters[key].default != Signature.empty:
            default = sig.parameters[key].default
            result[key]['required'] = False
            result[key]['default'] = default
            if type(default) in json_types:
                default_type = type(default)
        arg_type = default_type
        if sig.parameters[key].annotation != Signature.empty:
            arg_type = sig.parameters[key].annotation
            if type(arg_type) == _TypedDictMeta:
                result[key]['type'] = 'object'
                result[key]['properties'] = mk_sub_dict_spec_from_typed_dict(arg_type)
                continue
            elif getattr(arg_type, '_name', None) == 'Iterable':
                result[key]['items'] = mk_sub_list_spec_from_iterable(arg_type)
                arg_type = list
            elif arg_type not in json_types and not complex_type_mapping.get(arg_type):
                arg_type = str(default_type)
        else:
            arg_type = default_type
        result[key]['type'] = arg_type
    return result


# def mk_input_validator_from_spec(spec):
#     def input_validator(input_args, input_kwargs):
#         for arg_spec in input_spec:
#             
