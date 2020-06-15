import inspect
import re


def create_handler(input_class, methodname):
    constructor_arg_names = [argname for argname in inspect.signature(input_class)][1:]
    class_method = input_class.getattr(methodname)

    def handler(*input_args, **input_kwargs):
        constructor_kwargs = {input_kwargs.pop(argname, None) for argname in constructor_arg_names}
        instance = input_class(**constructor_kwargs)
        return instance.getattr(methodname)(*input_args, **input_kwargs)
    handler.input_trans = class_method.getattr('input_trans', None)
    handler.input_validator = class_method.getattr('input_validator', None)
    handler.output_trans = class_method.getattr('output_trans', None)
    return handler


def mk_functions_from_class(input_class, whitelist=None, name_regex=None):
    def allowed_method(methodname):
        if whitelist and methodname in whitelist:
            return True
        if name_regex:
            return re.match(name_regex, methodname)
        return methodname[0] != '_'
    methods = [m for m in inspect.getmembers(input_class, predicate=callable) if
               allowed_method(m[0][0])]

    return [create_handler(input_class, method) for method in methods]
