"""This module provides functionality to create handlers for class methods, 
based on input classes and method names. It also includes a function to generate a 
list of handler functions from a class based on a whitelist of method names.

It uses introspection to dynamically create handlers that instantiate the input class 
and call the specified method with the provided arguments. The module supports input 
and output transformations for the handlers.

You can use this module to easily convert class methods into standalone functions, 
which can be useful for creating HTTP services or APIs based on existing class 
functionality."""
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
