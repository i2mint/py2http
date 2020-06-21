from functools import reduce
from inspect import Signature, Parameter, _ParameterKind, signature
from typing import Any
from collections import UserDict

from collections.abc import Mapping
from typing import Union, Callable

_empty = Parameter.empty

from inspect import _empty

from typing import Union, Callable, Iterable
from typing import Mapping as MappingType

ParamsType = Iterable[Parameter]
ParamsAble = Union[ParamsType, MappingType[str, Parameter], Callable]
SignatureAble = Union[Signature, Callable, ParamsType, MappingType[str, Parameter]]


def assure_callable(obj: SignatureAble):
    if isinstance(obj, Callable):
        return obj
    else:
        def f(*args, **kwargs):
            """Empty function made just to carry a signature"""

        f.__signature__ = assure_signature(obj)
        return f


def assure_signature(obj: SignatureAble):
    if isinstance(obj, Signature):
        return obj
    elif isinstance(obj, Callable):
        return Signature.from_callable(obj)
    elif isinstance(obj, Iterable):
        try:
            params = assure_params(obj)
            return Signature(parameters=params)
        except TypeError:
            raise TypeError(f"Don't know how to make that object into a Signature: {obj}")


def assure_params(obj: ParamsAble):
    if isinstance(obj, Iterable):
        if isinstance(obj, Mapping):
            obj = obj.values()
        obj = list(obj)
        if len(obj) == 0 or isinstance(obj[0], Parameter):
            return obj
        elif isinstance(obj[0], dict):
            return [Parameter(**x) for x in obj]
    else:
        if isinstance(obj, Callable):
            obj = Signature.from_callable(obj)
        if isinstance(obj, Signature):
            return list(obj.parameters.values())
    # if function didn't return at this point, it didn't find a match, so raise
    raise TypeError(
        f"Don't know how to make that object into an iterable of inspect.Parameter objects: {obj}")


class MissingArgValFor(object):
    """A simple class to wrap an argument name, indicating that it was missing somewhere.
    >>> MissingArgValFor('argname')
    MissingArgValFor("argname")
    """

    def __init__(self, argname: str):
        assert isinstance(argname, str)
        self.argname = argname

    def __repr__(self):
        return f'MissingArgValFor("{self.argname}")'


# TODO: Look into the handling of the Parameter.VAR_KEYWORD kind in params
def extract_arguments(params: ParamsAble,
                      *,
                      include_all_when_var_keywords_in_params=False,
                      assert_no_missing_position_only_args=False,
                      **kwargs
                      ):
    """Extract arguments needed to satisfy the params of a callable, dealing with the dirty details.

    Returns an (param_args, param_kwargs, remaining_kwargs) tuple where
    - param_args are the values of kwargs that are PO (POSITION_ONLY) as defined by params,
    - param_kwargs are those names that are both in params and not in param_args, and
    - remaining_kwargs are the remaining.

    Intended usage: When you need to call a function `func` that has some position-only arguments,
    but you have a kwargs dict of arguments in your hand. You can't just to `func(**kwargs)`.
    But you can (now) do
    ```
    args, kwargs, remaining = kwargs_to_args_kwargs(kwargs, func)  # extract from kwargs what you need for func
    # ... check if remaing is empty (or not) depending on your paranoia, and then call the func:
    func(*args, **kwargs)
    ```
    (And if you doing that a lot: Do put it in a decorator!)

    See this function too: kwargs_to_args_kwargs.without_remainding

    :param params: Specifies what PO arguments should be extracted.
        Could be a callable, Signature, iterable of Parameters...
    :param kwargs: The kwargs to extract the args from
    :return: A (param_args, param_kwargs, remaining_kwargs) tuple.

    The most frequent case you'll encounter is when there's no POSITION_ONLY args, your param_args will be empty
    and you param_kwargs will contain all the arguments that match params, in the order of these params.

    >>> from inspect import signature
    >>> def f(a, b, c=None, d=0): ...
    >>> extract_arguments(f, b=2, a=1, c=3, d=4, extra='stuff')
    ((), {'a': 1, 'b': 2, 'c': 3, 'd': 4}, {'extra': 'stuff'})

    But sometimes you do have POSITION_ONLY arguments.
    What extract_arguments will do for you is return the value of these as the first element of
    the triple.
    >>> def f(a, b, c=None, /, d=0): ...
    >>> extract_arguments(f, b=2, a=1, c=3, d=4, extra='stuff')
    ((1, 2, 3), {'d': 4}, {'extra': 'stuff'})

    Note above how we get `(1, 2, 3)`, the order defined by the func's signature,
    instead of `(2, 1, 3)`, the order defined by the kwargs.
    So it's the params (e.g. function signature) that determine the order, not kwargs.
    When using to call a function, this is especially crucial if we use POSITION_ONLY arguments.

    See also that the third output, the remaining_kwargs, as `{'extra': 'stuff'}` since
    it was not in the params of the function.
    Even if you include a VAR_KEYWORD kind of argument in the function, it won't change
    this behavior.

    >>> def f(a, b, c=None, /, d=0, **kws): ...
    >>> extract_arguments(f, b=2, a=1, c=3, d=4, extra='stuff')
    ((1, 2, 3), {'d': 4}, {'extra': 'stuff'})

    This is because we don't want to assume that all the kwargs can actually be
    included in a call to the function behind the params.
    Instead, the user can chose whether to include the remainder by doing a:
    ```
    param_kwargs.update(remaining_kwargs)
    ```
    et voilà.

    That said, we do understand that it may be a common pattern, so we'll do that extra step for you
    if you specify `include_all_when_var_keywords_in_params=True`.

    >>> def f(a, b, c=None, /, d=0, **kws): ...
    >>> extract_arguments(f, b=2, a=1, c=3, d=4, extra='stuff',
    ...                     include_all_when_var_keywords_in_params=True)
    ((1, 2, 3), {'d': 4, 'extra': 'stuff'}, {})

    And what happens if the kwargs doesn't contain all the POSITION_ONLY arguments?

    >>> def f(a, b, c=None, /, d=0): ...
    >>> extract_arguments(f, b=2, d='is a kw arg', e='is not an arg at all')
    ((MissingArgValFor("a"), 2, MissingArgValFor("c")), {'d': 'is a kw arg'}, {'e': 'is not an arg at all'})

    A few more examples...

    Let's call `extract_arguments` with params being not a function,
    but, a Signature instance, a mapping whose values are Parameter instances,
    or an iterable of Parameter instances...

    >>> def func(a, b,  /, c=None, *, d=0, **kws): ...
    >>> sig = Signature.from_callable(func)
    >>> param_map = sig.parameters
    >>> param_iterable = param_map.values()
    >>> kwargs = dict(b=2, a=1, c=3, d=4, extra='stuff')
    >>> assert extract_arguments(sig, **kwargs) == extract_arguments(func, **kwargs)
    >>> assert extract_arguments(param_map, **kwargs) == extract_arguments(func, **kwargs)
    >>> assert extract_arguments(param_iterable, **kwargs) == extract_arguments(func, **kwargs)

    Edge case:
    No params specified? No problem. You'll just get empty args and kwargs. Everything in the remainder
    >>> extract_arguments(params=(), b=2, a=1, c=3, d=0)
    ((), {}, {'b': 2, 'a': 1, 'c': 3, 'd': 0})
    """

    params = assure_params(params)
    if not params:
        return (), {}, {k: v for k, v in kwargs.items()}

    params_names = tuple(p.name for p in params)
    names_for_args = [p.name for p in params if p.kind == Parameter.POSITIONAL_ONLY]
    param_kwargs_names = [x for x in params_names if x not in set(names_for_args)]
    remaining_names = [x for x in kwargs if x not in params_names]

    param_args = tuple(kwargs.get(k, MissingArgValFor(k)) for k in names_for_args)
    param_kwargs = {k: kwargs[k] for k in param_kwargs_names if k in kwargs}
    remaining_kwargs = {k: kwargs[k] for k in remaining_names}

    if include_all_when_var_keywords_in_params:
        if next((p.name for p in params if p.kind == Parameter.VAR_KEYWORD), None) is not None:
            param_kwargs.update(remaining_kwargs)
            remaining_kwargs = {}

    if assert_no_missing_position_only_args:
        missing_argnames = tuple(x.argname for x in param_args if isinstance(x, MissingArgValFor))
        assert missing_argnames, f"There were some missing positional only argnames: {missing_argnames}"

    return param_args, param_kwargs, remaining_kwargs


def _extract_arguments_without_remaining(params, **kwargs):
    param_args, param_kwargs, _ = extract_arguments(params, **kwargs)
    return param_args, param_kwargs


extract_arguments.without_remaining = _extract_arguments_without_remaining


class Param(Parameter):
    # aliases
    PK = Parameter.POSITIONAL_OR_KEYWORD
    OP = Parameter.POSITIONAL_ONLY
    OK = Parameter.KEYWORD_ONLY
    VP = Parameter.VAR_POSITIONAL
    VK = Parameter.VAR_KEYWORD

    def __init__(self, name, kind=PK, *, default=_empty, annotation=_empty):
        super().__init__(name, kind, default=default, annotation=annotation)


class Params(UserDict):
    """

    >>> def foo(a, b: int, c=None, d: str='hi') -> int: ...
    >>> def bar(b: float, d='hi'): ...
    >>> Params(foo)
    {'a': <Parameter "a">, 'b': <Parameter "b: int">, 'c': <Parameter "c=None">, 'd': <Parameter "d: str = 'hi'">}
    >>> p = Params(bar)
    >>> Params(p['b'])
    {'b': <Parameter "b: float">}
    >>> Params()
    {}
    >>> Params([p['d'], p['b']])
    {'d': <Parameter "d='hi'">, 'b': <Parameter "b: float">}
    """

    def __init__(self, obj=None, validate=True):
        if obj is None:
            params_dict = dict()
        elif callable(obj):
            params_dict = dict(signature(obj).parameters)
        elif isinstance(obj, Parameter):
            params_dict = {obj.name: obj}
        else:
            try:
                params_dict = dict(obj)
            except TypeError:
                params_dict = {x.name: x for x in obj}

        super().__init__(params_dict)
        # if validate:
        #     self.validate()

    @staticmethod
    def foo(obj=None):
        if obj is None:
            params_dict = dict()
        elif callable(obj):
            params_dict = dict(signature(obj).parameters)
        elif isinstance(obj, Parameter):
            params_dict = {obj.name: obj}
        else:
            try:
                params_dict = dict(obj)
            except TypeError:
                params_dict = {x.name: x for x in obj}

        return params_dict

    @classmethod
    def from_signature(cls, sig):
        """

        :param sig:
        :return:

        >>> from inspect import signature, Signature
        >>> def foo(a, b: int, c=None, d: str='hi') -> int: ...
        >>> sig = signature(foo)
        >>> assert isinstance(sig, Signature)
        >>> params = Params.from_signature(sig)
        >>> params
        """
        return cls(sig.parameters.values())

    @classmethod
    def from_callable(cls, obj):
        return cls.from_signature(signature(obj))

    def __add__(self, params):
        if isinstance(params, Parameter):
            self.__class__([params])
        elif isinstance(params, Signature):
            self.__class__.from_signature(params)
        else:
            pass

    def __setitem__(self, k, v):
        pass

    def validate(self):
        for k, v in self.items():
            assert isinstance(k, str), f"isinstance({k}, str)"
            assert isinstance(v, Parameter), f"isinstance({v}, Parameter)"
        return True


class Sig(Signature):
    @classmethod
    def from_params(cls, params):
        if isinstance(params, Parameter):
            params = (params,)
        return cls(params)

    def __add__(self, sig):
        pass


def mk_sig(obj: Union[Signature, Callable, Mapping, None] = None, return_annotations=_empty, **annotations):
    """Convenience function to make a signature or inject annotations to an existing one.

    Note: If you don't need
    >>> s = mk_sig(lambda a, b, c=1, d='bar': ..., b=int, d=str)
    >>> s
    <Signature (a, b: int, c=1, d: str = 'bar')>
    >>> # showing that sig can take a signature input, and overwrite an existing annotation:
    >>> mk_sig(s, a=list, b=float)  # note the b=float
    <Signature (a: list, b: float, c=1, d: str = 'bar')>
    >>> mk_sig()
    <Signature ()>
    >>> mk_sig(lambda a, b=2, c=3: ..., d=int)  # trying to annotate an argument that doesn't exist
    Traceback (most recent call last):
    ...
    AssertionError: These argument names weren't found in the signature: {'d'}
    """
    if obj is None:
        return Signature()
    if callable(obj):
        obj = Signature.from_callable(obj)  # get a signature object from a callable
    if isinstance(obj, Signature):
        obj = obj.parameters  # get the parameters attribute from a signature
    params = dict(obj)  # get a writable copy of parameters
    if not annotations:
        return Signature(params.values(), return_annotation=return_annotations)
    else:
        assert set(annotations) <= set(params), \
            f"These argument names weren't found in the signature: {set(annotations) - set(params)}"
        for name, annotation in annotations.items():
            p = params[name]
            params[name] = Parameter(name=name, kind=p.kind, default=p.default, annotation=annotation)
        return Signature(params.values(), return_annotation=return_annotations)


def mk_sig_from_args(*args_without_default, **args_with_defaults):
    """Make a Signature instance by specifying args_without_default and args_with_defaults.
    >>> mk_sig_from_args('a', 'b', c=1, d='bar')
    <Signature (a, b, c=1, d='bar')>
    """
    assert all(isinstance(x, str) for x in args_without_default), "all default-less arguments must be strings"
    kind = Parameter.POSITIONAL_OR_KEYWORD
    params = [Parameter(name, kind=kind) for name in args_without_default]
    params += [Parameter(name, kind=kind, default=default) for name, default in args_with_defaults.items()]
    return Signature(params)


def insert_annotations(s: Signature, *, return_annotation=_empty, **annotations):
    """Insert annotations in a signature.
    (Note: not really insert but returns a copy of input signature)
    >>> from inspect import signature
    >>> s = signature(lambda a, b, c=1, d='bar': 0)
    >>> s
    <Signature (a, b, c=1, d='bar')>
    >>> ss = insert_annotations(s, b=int, d=str)
    >>> ss
    <Signature (a, b: int, c=1, d: str = 'bar')>
    >>> insert_annotations(s, b=int, d=str, e=list)
    Traceback (most recent call last):
    ...
    AssertionError: These argument names weren't found in the signature: {'e'}
    """
    assert set(annotations) <= set(s.parameters), \
        f"These argument names weren't found in the signature: {set(annotations) - set(s.parameters)}"
    params = dict(s.parameters)
    for name, annotation in annotations.items():
        p = params[name]
        params[name] = Parameter(name=name, kind=p.kind, default=p.default, annotation=annotation)
    return Signature(params.values(), return_annotation=return_annotation)


mappingproxy = type(Signature().parameters)


# PATTERN: tree crud pattern
def signature_to_dict(sig: Signature):
    return {'parameters': sig.parameters, 'return_annotation': sig.return_annotation}


# TODO: will we need more options for the priority argument? Like position?
def update_signature_with_signatures_from_funcs(*funcs, priority: str = 'last'):
    """Make a decorator that will merge the signatures of given funcs to the signature of the wrapped func.
    By default, the funcs signatures will be placed last, but can be given priority by asking priority = 'first'

    >>> def foo(a='a', b: int=0, c=None) -> int: ...
    >>> def bar(b: float=0.0, d: str='hi') -> float: ...
    >>> def something(y=(1, 2)): ...
    >>> def another(y=10): ...
    >>> @update_signature_with_signatures_from_funcs(foo, bar)
    ... def hello(x: str='hi', y=1) -> str:
    ...     pass
    >>> signature(hello)
    <Signature (x: str = 'hi', y=1, a='a', b: float = 0.0, c=None, d: str = 'hi')>
    >>>
    >>> # Try a different order and priority == 'first'. Notice the b arg type and default!
    >>> add_foobar_to_signature_first = update_signature_with_signatures_from_funcs(bar, foo, priority='first')
    >>> bar_foo_something = add_foobar_to_signature_first(something)
    >>> signature(bar_foo_something)
    <Signature (b: int = 0, d: str = 'hi', a='a', c=None, y=(1, 2))>
    >>> # See how you can reuse the decorator several times
    >>> bar_foo_another = add_foobar_to_signature_first(another)
    >>> signature(bar_foo_another)
    <Signature (b: int = 0, d: str = 'hi', a='a', c=None, y=10)>
    """
    if not isinstance(priority, str):
        raise TypeError("priority should be a string")

    if priority == 'last':
        def transform_signature(func):
            func.__signature__ = _merged_signatures_of_func_list([func] + list(funcs))
            return func
    elif priority == 'first':
        def transform_signature(func):
            func.__signature__ = _merged_signatures_of_func_list(list(funcs) + [func])
            return func
    else:
        raise ValueError("priority should be 'last' or 'first'")

    return transform_signature


def common_and_diff_argnames(func1: callable, func2: callable) -> dict:
    """Get list of argument names that are common to two functions, as well as the two lists of names that are different

    Args:
        func1: First function
        func2: Second function

    Returns: A dict with fields 'common', 'func1_not_func2', and 'func2_not_func1'

    >>> def f(t, h, i, n, k): ...
    >>> def g(t, w, i, c, e): ...
    >>> common_and_diff_argnames(f, g)
    {'common': ['t', 'i'], 'func1_not_func2': ['h', 'n', 'k'], 'func2_not_func1': ['w', 'c', 'e']}
    >>> common_and_diff_argnames(g, f)
    {'common': ['t', 'i'], 'func1_not_func2': ['w', 'c', 'e'], 'func2_not_func1': ['h', 'n', 'k']}
    """
    p1 = signature(func1).parameters
    p2 = signature(func2).parameters
    return {
        'common': [x for x in p1 if x in p2],
        'func1_not_func2': [x for x in p1 if x not in p2],
        'func2_not_func1': [x for x in p2 if x not in p1],
    }


dflt_name_for_kind = {
    Parameter.VAR_POSITIONAL: 'args',
    Parameter.VAR_KEYWORD: 'kwargs',
}

arg_order_for_param_tuple = ('name', 'default', 'annotation', 'kind')


def mk_param(param, dflt_kind=Parameter.POSITIONAL_OR_KEYWORD):
    """Make an inspect.Parameter object with less boilerplate verbosity.
    Args:
        param: Can be an inspect.Parameter itself, or something resolving to it:
            - a string: Will be considered to be the argument name
            - an inspect._ParameterKind type: Can only be Parameter.VAR_KEYWORD or Parameter.VAR_POSITIONAL,
                will be taken as the kind, and the name will be decided according to the dflt_name_for_kind mapping.
            - a tuple: Will use the arg_order_for_param_tuple to resolve what Parameter constructor arguments
                the elements of the tuple correspond to.
        dflt_kind: Default kind (of type _ParameterKind) to use if no other kind is specified.

    Returns:
        An inspect.Parameter object

    See mk_signature for uses
    """
    if isinstance(param, str):  # then consider param to be the argument name
        param = dict(name=param)
    elif isinstance(param, _ParameterKind):  # then consider param to be the argument kind
        name = dflt_name_for_kind.get(param, None)
        if name is not None:
            param = dict(name=name, kind=param)
        else:
            raise ValueError("If param is an inspect._ParameterKind, is must be VAR_POSITIONAL or VAR_KEYWORD")
    elif isinstance(param, tuple):
        param = dict(zip(arg_order_for_param_tuple, param))

    if isinstance(param, dict):
        param = dict({'kind': dflt_kind}, **param)
        param = Parameter(**param)

    assert isinstance(param, Parameter), "param should be an inspect.Parameter at this point!"
    return param


def mk_signature(parameters, *, return_annotation=_empty, __validate_parameters__=True):
    """Make an inspect.Signature object with less boilerplate verbosity.
    Args:
        signature: A list of parameter specifications. This could be an inspect.Parameter object or anything that
            the mk_param function can resolve into an inspect.Parameter object.
        return_annotation: Passed on to inspect.Signature.
        __validate_parameters__: Passed on to inspect.Signature.

    Returns:
        An inspect.Signature object

    >>> mk_signature(['a', 'b', 'c'])
    <Signature (a, b, c)>
    >>> mk_signature(['a', ('b', None), ('c', 42, int)])  # specifying defaults and annotations
    <Signature (a, b=None, c: int = 42)>
    >>> import inspect
    >>> mk_signature(['a', ('b', inspect._empty, int)])  # specifying an annotation without a default
    <Signature (a, b: int)>
    >>> mk_signature(['a', 'b', 'c'], return_annotation=str)  # specifying return annotation
    <Signature (a, b, c) -> str>
    >>>
    >>> # But you can always specify parameters the "long" way
    >>> mk_signature([inspect.Parameter(name='kws', kind=inspect.Parameter.VAR_KEYWORD)], return_annotation=str)
    <Signature (**kws) -> str>
    >>>
    >>> # Note that mk_signature is an inverse of signature_to_dict:
    >>> def foo(a, b: int=0, c=None) -> int: ...
    >>> sig_foo = signature(foo)
    >>> assert mk_signature(**signature_to_dict(sig_foo)) == sig_foo
    """
    if isinstance(parameters, Signature):
        parameters = parameters.parameters.values()
    elif isinstance(parameters, (mappingproxy, dict)):
        parameters = parameters.values()
    else:
        parameters = list(map(mk_param, parameters))

    return Signature(parameters,
                     return_annotation=return_annotation, __validate_parameters__=__validate_parameters__)


def set_signature_of_func(func, parameters, *, return_annotation=_empty, __validate_parameters__=True):
    """Set the signature of a function, with sugar.

    Args:
        func: Function whose signature you want to set
        signature: A list of parameter specifications. This could be an inspect.Parameter object or anything that
            the mk_param function can resolve into an inspect.Parameter object.
        return_annotation: Passed on to inspect.Signature.
        __validate_parameters__: Passed on to inspect.Signature.

    Returns:
        None (but sets the signature of the input function)

    >>> import inspect
    >>> def foo(*args, **kwargs):
    ...     pass
    ...
    >>> inspect.signature(foo)
    <Signature (*args, **kwargs)>
    >>> set_signature_of_func(foo, ['a', 'b', 'c'])
    >>> inspect.signature(foo)
    <Signature (a, b, c)>
    >>> set_signature_of_func(foo, ['a', ('b', None), ('c', 42, int)])  # specifying defaults and annotations
    >>> inspect.signature(foo)
    <Signature (a, b=None, c: int = 42)>
    >>> set_signature_of_func(foo, ['a', 'b', 'c'], return_annotation=str)  # specifying return annotation
    >>> inspect.signature(foo)
    <Signature (a, b, c) -> str>
    >>> # But you can always specify parameters the "long" way
    >>> set_signature_of_func(
    ...  foo,
    ...  [inspect.Parameter(name='kws', kind=inspect.Parameter.VAR_KEYWORD)], return_annotation=str)
    >>> inspect.signature(foo)
    <Signature (**kws) -> str>

    """
    func.__signature__ = mk_signature(parameters,
                                      return_annotation=return_annotation,
                                      __validate_parameters__=__validate_parameters__)
    # Not returning func so it's clear(er) that the function is transformed in place


# TODO: It seems the better choice would be to oblige the user to deal with return annotation explicitly

def _merge_sig_dicts(sig1_dict, sig2_dict):
    """Merge two signature dicts. A in dict.update(sig1_dict, **sig2_dict), but specialized for signature dicts.
    If sig1_dict and sig2_dict both define a parameter or return annotation, sig2_dict decides on what the output is.
    """
    return {
        'parameters':
            dict(sig1_dict['parameters'], **sig2_dict['parameters']),
        'return_annotation':
            sig2_dict['return_annotation'] or sig1_dict['return_annotation']
    }


var_kinds = {Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD}


def _merge_signatures(sig1, sig2):
    """Get the merged signatures of two signatures (sig2 is the final decider of conflics)
    >>> def foo(a='a', b: int=0, c=None) -> int: ...
    >>> def bar(b: float=0.0, d: str='hi') -> float: ...
    >>> foo_sig = signature(foo)
    >>> bar_sig = signature(bar)
    >>> foo_sig
    <Signature (a='a', b: int = 0, c=None) -> int>
    >>> bar_sig
    <Signature (b: float = 0.0, d: str = 'hi') -> float>
    >>> _merge_signatures(foo_sig, bar_sig)
    <Signature (a='a', b: float = 0.0, c=None, d: str = 'hi') -> float>
    >>> _merge_signatures(bar_sig, foo_sig)
    <Signature (b: int = 0, d: str = 'hi', a='a', c=None) -> int>
    """
    sig1_dict = signature_to_dict(sig1)
    # remove variadic kinds from sig1
    sig1_dict['parameters'] = {k: v for k, v in sig1_dict['parameters'].items() if v.kind not in var_kinds}
    return mk_signature(**_merge_sig_dicts(sig1_dict, signature_to_dict(sig2)))


def _merge_signatures_of_funcs(func1, func2):
    """Get the merged signatures of two functions (func2 is the final decider of conflics)
    >>> def foo(a='a', b: int=0, c=None) -> int: ...
    >>> def bar(b: float=0.0, d: str='hi') -> float: ...
    >>> _merge_signatures_of_funcs(foo, bar)
    <Signature (a='a', b: float = 0.0, c=None, d: str = 'hi') -> float>
    >>> _merge_signatures_of_funcs(bar, foo)
    <Signature (b: int = 0, d: str = 'hi', a='a', c=None) -> int>
    """
    return _merge_signatures(signature(func1), signature(func2))


def _merged_signatures_of_func_list(funcs, return_annotation: Any = _empty):
    """
    >>> def foo(a='a', b: int=0, c=None) -> int: ...
    >>> def bar(b: float=0.0, d: str='hi') -> float: ...
    >>> def hello(x: str='hi', y=1) -> str: ...
    >>>
    >>> # Test how the order of the functions affect the order of the parameters
    >>> _merged_signatures_of_func_list([foo, bar, hello])
    <Signature (a='a', b: float = 0.0, c=None, d: str = 'hi', x: str = 'hi', y=1)>
    >>> _merged_signatures_of_func_list([hello, foo, bar])
    <Signature (x: str = 'hi', y=1, a='a', b: float = 0.0, c=None, d: str = 'hi')>
    >>> _merged_signatures_of_func_list([foo, bar, hello])
    <Signature (a='a', b: float = 0.0, c=None, d: str = 'hi', x: str = 'hi', y=1)>
    >>>
    >>> # Test the return_annotation argument
    >>> _merged_signatures_of_func_list([foo, bar], list)  # specifying that the return type is a list
    <Signature (a='a', b: float = 0.0, c=None, d: str = 'hi') -> list>
    >>> _merged_signatures_of_func_list([foo, bar], foo)  # specifying that the return type is a list
    <Signature (a='a', b: float = 0.0, c=None, d: str = 'hi') -> int>
    >>> _merged_signatures_of_func_list([foo, bar], bar)  # specifying that the return type is a list
    <Signature (a='a', b: float = 0.0, c=None, d: str = 'hi') -> float>
    """

    s = reduce(_merge_signatures, map(signature, funcs))

    if return_annotation in funcs:  # then you want the return annotation of a specific func of funcs
        return_annotation = signature(return_annotation).return_annotation

    return s.replace(return_annotation=return_annotation)


############# Tools for testing ########################################################################################
from functools import partial


def param_for_kind(name=None, kind='positional_or_keyword', with_default=False, annotation=Parameter.empty):
    """Function to easily and flexibly make inspect.Parameter objects for testing.

    It's annoying to have to compose parameters from scratch to testing things.
    This tool should help making it less annoying.

    >>> from py2mint.signatures import param_kinds
    >>> list(map(param_for_kind, param_kinds))
    [<Parameter "POSITIONAL_ONLY">, <Parameter "POSITIONAL_OR_KEYWORD">, <Parameter "VAR_POSITIONAL">, <Parameter "KEYWORD_ONLY">, <Parameter "VAR_KEYWORD">]
    >>> param_for_kind.positional_or_keyword()
    <Parameter "POSITIONAL_OR_KEYWORD">
    >>> param_for_kind.positional_or_keyword('foo')
    <Parameter "foo">
    >>> param_for_kind.keyword_only()
    <Parameter "KEYWORD_ONLY">
    >>> param_for_kind.keyword_only('baz', with_default=True)
    <Parameter "baz='dflt_keyword_only'">
    """
    name = name or f"{kind}"
    kind_obj = getattr(Parameter, str(kind).upper())
    kind = str(kind_obj).lower()
    default = f"dflt_{kind}" if with_default and kind not in {'var_positional', 'var_keyword'} else Parameter.empty
    return Parameter(name=name,
                     kind=kind_obj,
                     default=default,
                     annotation=annotation)


param_kinds = list(filter(lambda x: x.upper() == x, Parameter.__dict__))

for kind in param_kinds:
    lower_kind = kind.lower()
    setattr(param_for_kind, lower_kind,
            partial(param_for_kind, kind=kind))
    setattr(param_for_kind, 'with_default',
            partial(param_for_kind, with_default=True))
    setattr(getattr(param_for_kind, lower_kind), 'with_default',
            partial(param_for_kind, kind=kind, with_default=True))
    setattr(getattr(param_for_kind, 'with_default'), lower_kind,
            partial(param_for_kind, kind=kind, with_default=True))
