import inspect
import re
from typing import Iterable


def create_handler(input_class, methodname):
    constructor_arg_names = [argname for argname in inspect.signature(input_class)][1:]
    class_method = input_class.getattr(methodname)

    def handler(*input_args, **input_kwargs):
        constructor_kwargs = {
            input_kwargs.pop(argname, None) for argname in constructor_arg_names
        }
        instance = input_class(**constructor_kwargs)
        return instance.getattr(methodname)(*input_args, **input_kwargs)

    handler.input_trans = class_method.getattr('input_trans', None)
    handler.output_trans = class_method.getattr('output_trans', None)
    return handler


def mk_functions_from_class(input_class, whitelist):
    if isinstance(whitelist, Iterable):
        whitelist = re.compile('(' + '|'.join(whitelist) + ')$').match
    elif isinstance(whitelist, str):
        whitelist = re.compile(whitelist).match
    assert callable(
        whitelist
    ), f'whitelist needs to be an iterable, string, or callable. Was: {whitelist}'

    methods = [
        m
        for m in inspect.getmembers(input_class, predicate=callable)
        if whitelist(m[0][0])
    ]
    return [create_handler(input_class, method) for method in methods]
