import inspect
import re
from typing import Iterable


def create_handler(input_class, methodname):
    constructor_arg_names = [argname for argname in inspect.signature(input_class)][1:]
    class_method = input_class.getattr(methodname)

    def handler(**input_kwargs):
        constructor_kwargs = {input_kwargs.pop(argname, None) for argname in constructor_arg_names}
        instance = input_class(**constructor_kwargs)
        return instance.getattr(methodname)(**input_kwargs)

    handler.input_trans = class_method.getattr('input_trans', None)
    handler.input_validator = class_method.getattr('input_validator', None)
    handler.output_trans = class_method.getattr('output_trans', None)
    return handler


# TODO: Consider merging whitelist and regex.
# TODO: Default ("everything but what starts with _") could be dangerous
# TODO: See _proposal_mk_functions_from_class
def mk_functions_from_class(input_class, whitelist=None, name_regex=None):
    def allowed_method(methodname):
        if whitelist and methodname in whitelist:
            return True
        if name_regex:
            return re.match(name_regex, methodname)
        return not methodname.startswith('_')

    methods = [m for m in inspect.getmembers(input_class, predicate=callable) if
               allowed_method(m[0][0])]

    return [create_handler(input_class, method) for method in methods]


def _proposal_mk_functions_from_class(input_class, whitelist):
    if isinstance(whitelist, Iterable):
        whitelist = re.compile('(' + '|'.join(whitelist) + ')$').match
    elif isinstance(whitelist, str):
        whitelist = re.compile(whitelist).match
    assert callable(whitelist), \
        f"whitelist needs to be an iterable, string, or callable. Was: {whitelist}"

    methods = [m for m in inspect.getmembers(input_class, predicate=callable) if
               whitelist(m[0][0])]
    return [create_handler(input_class, method) for method in methods]
