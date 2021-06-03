from inspect import signature, Signature, Parameter
from typing import Any, _TypedDictMeta, T_co, Union, _GenericAlias
from i2.errors import InputError

COMPLEX_TYPE_MAPPING = {}
JSON_TYPES = [list, str, int, float, dict, bool]


def mk_sub_dict_schema_from_typed_dict(typed_dict):
    total = getattr(typed_dict, '__total__', False)
    required_properties = []

    def set_property(key, value):
        optional = False
        if getattr(value, '__origin__', None) == Union:
            optional = type(None) in value.__args__
            value = [x for x in value.__args__ if type(None) != x][0]
        if total and not optional:
            required_properties.append(key)
        if value in JSON_TYPES:
            properties[key]['type'] = value
        elif getattr(value, '_name', None) == 'Iterable':
            properties[key]['type'] = list
            properties[key]['items'] = mk_sub_list_schema_from_iterable(value)
        elif isinstance(value, _TypedDictMeta):
            properties[key]['type'] = dict
            (
                sub_dict_props,
                sub_dict_required_props,
            ) = mk_sub_dict_schema_from_typed_dict(value)
            properties[key]['properties'] = sub_dict_props
            if sub_dict_required_props:
                properties[key]['required'] = sub_dict_required_props

    properties = {}
    for key, value in typed_dict.__annotations__.items():
        properties[key] = {}
        properties[key]['type'] = Any
        set_property(key, value)
    return properties, required_properties


def mk_sub_list_schema_from_iterable(iterable_type):
    result = {}
    items_type = iterable_type.__args__[0]
    if type(items_type) == _TypedDictMeta:
        result['type'] = dict
        sub_dict_props, sub_dict_required = mk_sub_dict_schema_from_typed_dict(
            items_type
        )
        result['properties'] = sub_dict_props
        if sub_dict_required:
            result['required'] = sub_dict_required
    elif getattr(items_type, '_name', None) == 'Iterable':
        result['type'] = list
        result['items'] = mk_sub_list_schema_from_iterable(items_type)
    elif items_type in JSON_TYPES:
        result['type'] = items_type
    else:
        result['type'] = Any
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
    ...     'type': dict,
    ...     'properties': {
    ...         'a': {'type': typing.Any},
    ...         'b': {'default': 0.0, 'type': float}},
    ...     'required': ['a']}
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
    ...     'type': dict,
    ...     'properties': {
    ...        'x': {'type': float},
    ...        'y': {'default': 1, 'type': int},
    ...        'z': {'type': int, 'default': 1}},
    ...     'required': ['x']}
    >>> assert got == expected, f"\\n  expected {expected}\\n  got {got}"
    """
    if not exclude_keys:
        exclude_keys = {}
    input_properties = {}
    required_properties = []
    input_schema = {'type': dict, 'properties': input_properties}
    params = signature(func).parameters
    for key, param in params.items():
        if key in exclude_keys:
            continue

        default_type = Any
        p = {}
        if param.default != Parameter.empty:
            default = param.default
            if type(default) in JSON_TYPES:
                default_type = type(default)
            p['default'] = default
        elif (
            param.kind == Parameter.VAR_POSITIONAL
        ):  # TODO: See how to handle a tuple instead of a list (not JSON compatible)
            p['default'] = []
            default_type = list
        elif param.kind == Parameter.VAR_KEYWORD:
            p['default'] = {}
            default_type = dict
        else:
            required_properties.append(key)

        arg_type = default_type  # TODO: Not used. Check why (seems the if clause does covers all)
        if param.annotation != Signature.empty:
            arg_type = param.annotation
            if isinstance(arg_type, _TypedDictMeta):
                (
                    sub_dict_props,
                    sub_dict_required,
                ) = mk_sub_dict_schema_from_typed_dict(arg_type)
                p['properties'] = sub_dict_props
                if sub_dict_required:
                    p['required'] = sub_dict_required
                arg_type = dict
            elif getattr(arg_type, '_name', None) == 'Iterable':
                p['items'] = mk_sub_list_schema_from_iterable(arg_type)
                arg_type = list
            elif arg_type not in JSON_TYPES and not COMPLEX_TYPE_MAPPING.get(arg_type):
                arg_type = default_type
        p['type'] = arg_type

        if include_func_params:
            p['x-py-param'] = param
        # map key to this p info
        input_properties[key] = p
    if required_properties:
        input_schema['required'] = required_properties
    return input_schema


def mk_output_schema_from_func(func):
    result = {}
    sig = signature(func)
    output_type = sig.return_annotation
    # print(f'output_type: {output_type}')  # TODO: Remove: Use conditional logging instead
    if output_type in [Signature.empty, Any]:
        return {}
    if isinstance(output_type, _TypedDictMeta):
        result['type'] = dict
        result['properties'] = mk_sub_dict_schema_from_typed_dict(output_type)[0]
    elif getattr(output_type, '_name', None) == 'Iterable':
        result['type'] = list
        result['items'] = mk_sub_list_schema_from_iterable(output_type)
    elif output_type not in JSON_TYPES and not COMPLEX_TYPE_MAPPING.get(output_type):
        return {}
    else:
        result['type'] = output_type
    return result


def validate_input(raw_input: Any, schema: dict):
    def _validate_dict(input_value: dict, schema: dict, root_path: str):
        for param_name, spec in schema.items():
            param_path = f'{root_path}.{param_name}' if root_path else param_name
            if not isinstance(spec, dict):
                raise TypeError(
                    'Bad schema for input validation. Must contain dictionaries only.'
                )
            if param_name in input_value:
                param = input_value[param_name]
                _validate_input(param, spec, param_path)
            elif spec.get('required', False) and 'default' not in spec:
                errors.append(f'Parameter "{param_path}" is missing.')

    def _validate_input(param, spec, param_path):
        invalid_input_msg = (
            f'Invalid parameter "{param_path}"' if param_path else 'Invalid input'
        )
        param_type = spec.get('type', Any)
        if param_type != Any and not isinstance(param, param_type):
            errors.append(
                f'{invalid_input_msg}. Must be of type "{param_type.__name__}".'
            )
        elif param_type == list and 'items' in spec:
            for i, element in enumerate(param):
                _validate_input(element, spec['items'], f'{param_path}[{i}]')
        elif param_type == dict and 'properties' in spec:
            _validate_dict(param, spec['properties'], param_path)

    errors = []
    _validate_input(raw_input, schema, '')
    if len(errors) > 0:
        error_msg = ' '.join(errors)
        raise InputError(error_msg)


# TODO write this function to take the output from
# mk_input_schema_from_func and create a validator function
# that takes an input_kwargs dict and makes sure the type of each value
# matches the schema
# def mk_input_validator_from_schema(schema):
#     def input_validator(input_kwargs):
#         print('Your arguments are fallacious.')
#         return False


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
