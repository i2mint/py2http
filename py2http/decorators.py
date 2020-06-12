from inspect import signature, Signature

from inspect import signature, Signature, Parameter

from typing import Iterable, Callable, Union, Mapping
from functools import partial, wraps, update_wrapper
from types import FunctionType

ParameterKind = type(Parameter.POSITIONAL_OR_KEYWORD)  # to get the enum type

Params = Iterable[Parameter]
HasParams = Union[Iterable[Parameter], Mapping[str, Parameter], Signature, Callable]


def copy_func(f):
    """Copy a function (not sure it works with all types of callables)"""
    g = FunctionType(f.__code__, f.__globals__, name=f.__name__,
                     argdefs=f.__defaults__, closure=f.__closure__)
    g = update_wrapper(g, f)
    g.__kwdefaults__ = f.__kwdefaults__
    if hasattr(f, '__signature__'):
        g.__signature__ = f.__signature__
    return g


def transparently_wrapped(func):
    @wraps(func)
    def transparently_wrapped_func(*args, **kwargs):
        return func(args, **kwargs)

    return transparently_wrapped_func


def params_of(obj: HasParams):
    if isinstance(obj, Signature):
        obj = list(obj.parameters.values())
    elif isinstance(obj, Mapping):
        obj = list(obj.values())
    elif callable(obj):
        obj = list(signature(obj).parameters.values())
    assert all(isinstance(p, Parameter) for p in obj), "obj needs to be a Iterable[Parameter] at this point"
    return obj  # as is


def replace_with_params(target=None, /, *, source=None, inplace=False):
    """Will return a version of the target type that has params taken from source.
    Both target and source can be of the HasParams type, i.e.
    ```
        Union[Iterable[Parameter], Mapping[str, Parameter], Signature, Callable]
    ```

    >>> def f(a, /, b, *, c=None, **kwargs): ...
    ...
    >>> def g(x, y=1, *args, **kwargs): ...
    ...
    >>> f_sig = signature(f)
    >>> f_params_map = f_sig.parameters
    >>> f_params = tuple(f_params_map.values())
    >>> g_sig = signature(g)
    >>> g_params_map = g_sig.parameters
    >>> g_params = tuple(g_params_map.values())
    >>>
    >>> original_f_sig = signature(f)
    >>> print(original_f_sig)
    (a, /, b, *, c=None, **kwargs)
    >>> new_f = replace_with_params(f, source=g)
    >>> print(signature(new_f))
    (x, y=1, *args, **kwargs)
    >>> assert signature(new_f) == signature(g)
    >>> # but f remains unchanged (there is inplace=False option though!)
    >>> assert signature(f) == original_f_sig
    """
    if target is None:
        return partial(replace_with_params, source=source)
    else:
        if source is not None:
            new_params = params_of(source)
            if isinstance(target, Signature):
                # same return_annotation, but different params
                return Signature(new_params, target.return_annotation)
            elif isinstance(target, Mapping):
                # Note: params_of already asserts p are all Parameter instances
                return {p.name: p for p in new_params}
            elif callable(target):
                if not inplace:
                    target = copy_func(target)  # make a copy of the function so we don't
                target.__signature__ = Signature(new_params,
                                                 return_annotation=signature(target).return_annotation)
                return target
            else:
                return new_params
        else:
            return target


def params_replacer(replace: Union[dict, Callable[[Parameter], dict]],
                    obj: Iterable[Parameter]):
    """Generator of transformed params."""

    if isinstance(replace, dict):
        replace = lambda x: replace  # use the same replace on all parameters

    for p in params_of(obj):
        p = p.replace(**(replace(p) or {}))
        yield p


def tuple_the_args(func):
    """A decorator that will change a VAR_POSITIONAL (*args) argument to a tuple (args)
    argument of the same name.
    """
    params = params_of(func)
    is_vp = list(p.kind == VP for p in params)
    if any(is_vp):
        index_of_vp = is_vp.index(True)  # there's can be only one

        @wraps(func)
        def vpless_func(*args, **kwargs):
            # extract the element of args that needs to be unraveled
            a, _vp_args_, aa = args[:index_of_vp], args[index_of_vp], args[(index_of_vp + 1):]
            # call the original function with the unravelled args
            return func(*a, *_vp_args_, *aa, **kwargs)

        try:  # TODO: Avoid this try catch. Look in advance for default ordering
            params[index_of_vp] = params[index_of_vp].replace(kind=PK, default=())
            vpless_func.__signature__ = Signature(params,
                                                  return_annotation=signature(func).return_annotation)
        except ValueError:
            params[index_of_vp] = params[index_of_vp].replace(kind=PK)
            vpless_func.__signature__ = Signature(params,
                                                  return_annotation=signature(func).return_annotation)
        return vpless_func
    else:
        return copy_func(func)  # don't change anything (or should we wrap anyway, to be consistent?)


VP, PK, VK = (Parameter.VAR_POSITIONAL, Parameter.POSITIONAL_OR_KEYWORD, Parameter.VAR_KEYWORD)
var_param_types = {VP, VK}


def ch_signature_to_all_pk(sig):
    def changed_params():
        for p in sig.parameters.values():
            if p.kind not in var_param_types:
                yield p.replace(kind=PK)
            else:
                yield p

    return Signature(list(changed_params()), return_annotation=sig.return_annotation)


def ch_func_to_all_pk(func):
    """Returns a copy of the function where all arguments are of the PK kind.
    (PK: Positional_or_keyword)

    :param func: A callable
    :return:

    >>> from py2http.decorators import signature, ch_func_to_all_pk
    >>>
    >>> def f(a, /, b, *, c=None, **kwargs): ...
    ...
    >>> print(signature(f))
    (a, /, b, *, c=None, **kwargs)
    >>> ff = ch_func_to_all_pk(f)
    >>> print(signature(ff))
    (a, b, c=None, **kwargs)
    >>> def g(x, y=1, *args, **kwargs): ...
    ...
    >>> print(signature(g))
    (x, y=1, *args, **kwargs)
    >>> gg = ch_func_to_all_pk(g)
    >>> print(signature(gg))
    (x, y=1, *args, **kwargs)
    """
    func = tuple_the_args(func)
    sig = signature(func)
    func.__signature__ = ch_signature_to_all_pk(sig)
    return func


def flatten_callables(*callables, func_name=None):
    """
    Flatten a pipeline of calls into one function.
    """
    raise NotImplementedError("Meant to be a generalization of mk_flat")
    for call in callables:
        pass

    # def flat_func(**kwargs):
    #     for1 = {k: kwargs[k] for k in kwargs if k in sig1.parameters}
    #     for2 = {k: kwargs[k] for k in kwargs if k in sig2.parameters}
    #     instance = cls(**for1)  # TODO: implement caching option
    #     return getattr(instance, method)(**for2)
    #
    # flat_func.__signature__ = Signature(parameters, return_annotation=sig2.return_annotation)

    # if func_name is not None:
    #     flat_func.__name__ = func_name
    #
    # return flat_func


def mk_flat(cls, method, *, func_name="flat_func"):
    """
    Flatten a simple cls->instance->method call pipeline into one function.

    That is, a function mk_flat(cls, method) that returns a "flat function" such that
    ```
    cls(**init_kwargs).method(**method_kwargs) == flat_func(**init_kwargs, **method_kwargs)
    ```

    So, instead of this:
    ```graphviz
    label="NESTED: result = cls(**init_kwargs).method(**method_kwargs)"
    cls, init_kwargs -> instance
    instance, method, method_kwargs -> result
    ```
    you get a function `flat_func` that you can use like this:
    ```graphviz
    label="FLAT: result = flat_func(**init_kwargs, **method_kwargs)"
    flat_func, init_kwargs, method_kwargs -> result
    ```
    :param cls: A class
    :param method: A method of this class
    :param func_name: The name of the function (will be "flat_func" by default)
    :return:

    >>> class MultiplierClass:
    ...     def __init__(self, x):
    ...         self.x = x
    ...     def multiply(self, y: float = 1) -> float:
    ...         return self.x * y
    ...     def subtract(self, z):
    ...         return self.x - z
    ...
    >>> MultiplierClass(6).multiply(7)
    42
    >>> MultiplierClass(3.14).multiply()
    3.14
    >>> MultiplierClass(3).subtract(1)
    2
    >>> f = mk_flat(MultiplierClass, 'multiply', func_name='my_special_func')
    >>> help(f)
    Help on function my_special_func in module decorators:
    <BLANKLINE>
    my_special_func(x, y: float = 1) -> float
    <BLANKLINE>
    >>> f = mk_flat(MultiplierClass, MultiplierClass.subtract)
    >>> help(f)
    Help on function flat_func in module decorators:
    <BLANKLINE>
    flat_func(x, z)
    <BLANKLINE>
    """
    sig1 = signature(cls)
    if isinstance(method, str):
        method = getattr(cls, method)
    sig2 = signature(method)
    parameters = list(sig1.parameters.values()) + list(sig2.parameters.values())[1:]

    def flat_func(**kwargs):
        for1 = {k: kwargs[k] for k in kwargs if k in sig1.parameters}
        for2 = {k: kwargs[k] for k in kwargs if k in sig2.parameters}
        instance = cls(**for1)  # TODO: implement caching option
        return getattr(instance, method)(**for2)

    flat_func.__signature__ = Signature(parameters, return_annotation=sig2.return_annotation)
    flat_func.__name__ = func_name

    return flat_func


def add_attrs(**attrs):
    """Makes a function that adds attributes to a function.

    Used in it's normal context, it looks something like this:

    >>> @add_attrs(my_special_attr='my special value', another=42)
    ... def foo(x):
    ...     return x + 1
    >>>
    >>> foo(10)  # checking that this great function still works
    11
    >>> # checking that it now has some extra attributes
    >>> foo.my_special_attr
    'my special value'
    >>> foo.another
    42

    But it can be useful to make attribute adder, and reuse when needed.

    >>> brand_my_func = add_attrs(author="me")
    >>> _ = brand_my_func(foo)  # not capturing the output to show that the change happens in-place
    >>> foo.author
    'me'
    """

    def add_attrs_to_func(func):
        for attr_name, attr_val in attrs.items():
            setattr(func, attr_name, attr_val)
        return func

    return add_attrs_to_func


def http_get(func):
    func.http_method = 'get'
    return func


def http_post(func):
    func.http_method = 'post'
    return func


def http_put(func):
    func.http_method = 'put'
    return func


def http_delete(func):
    func.http_method = 'delete'
    return func


def route(route):
    def decorator(func):
        func.route = route
        return func

    return decorator


# TODO: stub
def mk_input_mapper(input_map):
    def decorator(func):
        return func

    return decorator
