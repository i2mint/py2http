from inspect import (
    signature,
    Signature,
    Parameter,
    isawaitable,
    iscoroutinefunction,
)
import inspect
import json
import pickle
from typing import Iterable, Callable, Union, Mapping
from functools import lru_cache, partial, wraps, update_wrapper
from json import JSONEncoder, dumps
from aiohttp import web
from bottle import response

# import collections
from typing import Awaitable, get_origin
from collections.abc import Awaitable as _Awaitable
import os

from i2.signatures import (
    set_signature_of_func,
    Sig,
    ch_func_to_all_pk,
    PK,
    KO,
)
from i2.errors import ModuleNotFoundIgnore

from py2http.schema_tools import mk_input_schema_from_func, validate_input
from py2http.config import AIOHTTP, BOTTLE
from py2http.constants import (
    JSON_CONTENT_TYPE,
    BINARY_CONTENT_TYPE,
    FORM_CONTENT_TYPE,
    RAW_CONTENT_TYPE,
    HTML_CONTENT_TYPE,
)


def ensure_awaitable_return_annot(func):
    """
    >>> async def foo(x: str) -> int: ...
    >>> assert str(signature(foo)) == '(x: str) -> int'
    >>> assert str(signature(ensure_awaitable_return_annot(foo))) == '(x: str) -> Awaitable[int]'
    >>>
    >>> # but if func is not async, don't change anything
    >>> def bar(a) -> str: ...
    >>> assert str(signature(bar)) == str(signature(ensure_awaitable_return_annot(bar)))  == '(a) -> str'
    >>>
    >>> # or if the return annotation is already contained in an Awaitable, don't change anything
    >>> async def baz() -> Awaitable[float]: ...
    >>> assert str(signature(baz)) == str(signature(ensure_awaitable_return_annot(baz))) == '() -> Awaitable[float]'
    """
    sig = signature(func)
    if (
        iscoroutinefunction(func)
        and sig.return_annotation != Signature.empty
        and get_origin(sig.return_annotation) != _Awaitable
    ):
        func.__signature__ = sig.replace(
            return_annotation=Awaitable[sig.return_annotation]
        )
    return func


def ignore_extra_arguments(func):
    sig = signature(func)

    @wraps(func)
    def wrapped_func(*args, **kwargs):
        t = sig.bind(*args, **kwargs)
        return func(*t.args, **t.kwargs)

    return wrapped_func


class Literal:
    """An object to indicate that the value should be considered literally"""

    def __init__(self, val):
        self.val = val


# TODO: Could easily be extended to included an "explicit=True" param (in __init_subclass__ kwargs)
#   that would indicate that decorator params need to be declared explicitly when
#   the "in the class body" trick is used. That is, one would have to say `deco_param = DecoParam(...)`
#   to declare such a param, instead of the current state which will consider all non-Literals
#   as a DecoParam.
class Decorator:
    """ A "transparent" decorator meant to be used to subclass into specialized decorators.

    The signature of the wrapped function is carried to the __call__ of the decorated instance.

    To specialize (and do something else than just "transparent" wrapping, you need to subclass
    Decorator and define your own `__call__` method. You may assume that

    The decorator pattern is a significant reuse tool, and indeed we use them a lot in i2i tooling.
    The standard way is to write decorators (and decorator factories) the functional was,
    but writing them as classes has introspection (therefore debuggability) advantages.

    The approach comes with other kinds of problems though.
    One of them is signature transfer (both for the decorator and the decorator factory).
    Taken care of here.

    Another wish (not really a problem) is to be able to use both `deco(func, params)`
    and `deco(params(func))` forms. Also taken care of here.

    Another problem is an increased boilerplate in specifying the decorator mechanics.
    For example: If you want to have a proper signature (not just **kwargs),
    you need to overwrite `__new__` for the sole purpose of specifying the arguments
    (names, and optional annotations and defaults).
    This problem is not taken care of here, but you can check out `Decora`,
    a subclass of Decorator, that does.

    >>> from py2http.decorators import Decorator
    >>> f = lambda x, y=1: x + y  # a function to decorate
    >>> f(10)
    11
    >>> signature(f)
    <Signature (x, y=1)>
    >>>
    >>> class LogCalls(Decorator):
    ...     def __new__(cls, func=None, *, verb='calling'):
    ...         return super().__new__(cls, func, verb=verb)
    ...
    ...     def __call__(self, *args, **kwargs):
    ...         print(f'{self.verb} {self.func.__name__} with {args} and {kwargs}')
    ...         return super().__call__(*args, **kwargs)
    ...
    >>> ff = LogCalls(f, verb='launching')  # doing it the "decorator way"
    >>> assert ff(10) == 11
    launching <lambda> with (10,) and {}
    >>> signature(ff)
    <Signature (x, y=1)>
    >>> assert signature(ff) == signature(f)  # asserting same signature as the wrapped f
    >>> signature(LogCalls)
    <Signature (func=None, *, verb='calling')>
    >>>
    >>> class ProcessOutput(Decorator):
    ...     def __new__(cls, func=None, *, postproc=None):
    ...         postproc = postproc or (lambda x: x)
    ...         return super().__new__(cls, func, postproc=postproc)
    ...
    ...     def __call__(self, *args, **kwargs):
    ...         return self.postproc(super().__call__(*args, **kwargs))
    ...
    >>>
    >>>
    >>> fff = ProcessOutput(postproc=str)(f)  # doing it the "decorator factory way"
    >>> assert fff(10) == "11"
    >>> assert signature(fff)  == signature(f)
    >>> signature(ProcessOutput)
    <Signature (func=None, *, postproc=None)>
    >>>
    >>> ff = LogCalls()(f)  # defaults work when using as factory
    >>> signature(ff)
    <Signature (x, y=1)>
    >>> ff(10)
    calling <lambda> with (10,) and {}
    11
    >>> ff = LogCalls(f)  # defaults work when using as decorator
    >>> ff(10)
    calling <lambda> with (10,) and {}
    11
    >>> LogCalls(f, real_arg=False)  # rejects arguments that weren't "registered" by the __new__
    Traceback (most recent call last):
        ...
    TypeError: __new__() got an unexpected keyword argument 'real_arg'
    """

    def __new__(cls, func=None, **kwargs):
        if func is None:
            return partial(cls, **kwargs)
        else:
            self = super().__new__(cls)
            self.func = func
            for attr_name, attr_val in kwargs.items():
                setattr(self, attr_name, attr_val)
            return update_wrapper(self, func)

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)


class DecoParameter(Parameter):
    """A Parameter object that is meant to be the a parameter of a decorator factory.
    Subclassing inspect.Parameter so that it can be distinguished from it if needed."""


class DecoParam:
    dflt_param_kind = Parameter.KEYWORD_ONLY

    def __init__(self, default=Parameter.empty, annotation=Parameter.empty):
        """Special object that will inject a DecoParameter into the class it's instantiated.

        DecoParameter is a inspect.Parameter that was subclassed for the sole purpose of being able to
        distinguish it from other possible Parameter objects.

        DecoParameter (like inspect.Parameter) needs a name and kind, and optional default and annotation.

        The name is taken from the variable name it's been assigned to.

        :param default: Optional default for the param (it's optional, though appears not to be by signature)
        :param annotation: Optional annotation for the param (it's optional, though appears not to be by signature)


        >>> from py2http.decorators import Decora, DecoParam
        >>>
        >>> class C:
        ...     w = DecoParam()
        ...     x = DecoParam(annotation=int)
        ...     y = DecoParam(default=42)
        ...     z = DecoParam(default='hello', annotation=str)
        ...
        >>> C.w
        <DecoParameter "w">
        >>> C.z
        <DecoParameter "z: str = 'hello'">
        >>>
        >>> from inspect import Signature
        >>> Signature((C.w, C.x, C.y, C.z))
        <Signature (*, w, x: int, y=42, z: str = 'hello')>

        """
        self.default = default
        self.annotation = annotation

    def __set_name__(self, owner, name):
        setattr(
            owner,
            name,
            DecoParameter(
                name,
                self.dflt_param_kind,
                default=self.default,
                annotation=self.annotation,
            ),
        )


from typing import Optional
import re

token_p = re.compile(r'\w+')


# TODO: Research how to keep the params in the order they were declared.
# TODO: Test the params order rule that is claimed.
class ParamsSpecifier:
    """A tool to specify params (that is, lists of inspect.Parameter instances that
    are used in callable signatures.

    But wait! you may not need this!

    Often the cleanest way to make a signature, or list of Parameters is to define an empty function
    with that signature, and extract it from there.

    See `Decora` for the original intended use of ParamsSpecifier.

    >>> from inspect import signature, Signature, Parameter
    >>> def f(a, b: int, c: float = 0.0, d: str='hi'): ...
    >>> sig = signature(f)
    >>> sig
    <Signature (a, b: int, c: float = 0.0, d: str = 'hi')>
    >>> list(sig.parameters.values())
    [<Parameter "a">, <Parameter "b: int">, <Parameter "c: float = 0.0">, <Parameter "d: str = 'hi'">]

    The reason for the existence of ParamsSpecifier was to do some magic around giving class-based
    decorators a signature. The reasons of this magic may be outdated soon.

    >>> from py2http.decorators import ParamsSpecifier
    >>> from inspect import Parameter, Signature
    >>> KO = Parameter.KEYWORD_ONLY
    >>>
    >>> class MyParams(ParamsSpecifier):
    ...     b = 3
    ...     z: float
    ...     c: int = 2
    ...
    >>> params = MyParams()()
    >>> expected_params = [
    ...     {'name': 'z', 'kind': KO, 'default': None, 'annotation': float},
    ...     {'name': 'b', 'kind': KO, 'default': 3},
    ...     {'name': 'c', 'kind': KO, 'default': 2, 'annotation': int}]
    >>> assert params == expected_params

    See that the params are all valid kwargs to inspect.Parameter, by making a signature from them
    >>> Signature(Parameter(**p) for p in params)
    <Signature (*, z: float = None, b=3, c: int = 2)>

    Let's now get another params specifier.

    >>> get_new_params = MyParams(
    ...     _annotations=dict(b=int, a=str),
    ...     _names='a wol',
    ...     another='here')
    >>> params = get_new_params()
    >>> expected_params = [
    ...     {'name': 'z', 'kind': KO, 'default': None, 'annotation': float},
    ...     {'name': 'b', 'kind': KO, 'default': 3, 'annotation': int},
    ...     {'name': 'c', 'kind': KO, 'default': 2, 'annotation': int},
    ...     {'name': 'another', 'kind': KO, 'default': 'here'},
    ...     {'name': 'a', 'kind': KO, 'default': None, 'annotation': str},
    ...     {'name': 'wol', 'kind': KO, 'default': None}]

    One thing to note in the expected_params is the order.
    Indeed, the order is not the order that is taken (because couldn't figure out otherwise)
    is as such:
    - First the class-level attributes that are annotated, but not given a default
        (though a blanket _dflt_default default will be given to them all).
        Here order is not assured.
    - Second the reset of the class-level attributes, in the order they were defined.
    - Third the instance argument params given by the _names argument, in the order they were listed.
    - Finally the instance argument name_and_dflts params, in the order they were listed.

    Remember, all this is meant to provide ways to specify signatures.

    >>> Signature(Parameter(**p) for p in params)
    <Signature (*, z: float = None, b: int = 3, c: int = 2, another='here', a: str = None, wol=None)>

    Now, not that ParamsSpecifier is the tool for this, but to demo what ParamsSpecifier's
    params are, we'll give one last example where we take a function, make a ParamsSpecifier
    from it, and add a different kind of default

    >>> def f(a, b: int, c: float = 0.0, d: str='hi'): ...
    >>> param_maker = ParamsSpecifier.from_func(f, _dflt_default='a different dflt')
    >>> Signature(Parameter(**p) for p in param_maker())
    <Signature (*, a='a different dflt', b: int = 'a different dflt', c: float = 0.0, d: str = 'hi')>
    """

    # _name_and_dflts = {}

    def __init__(
        self,
        _annotations: Optional[dict] = None,
        _names: str = '',
        _dflt_default=None,
        _kind=Parameter.KEYWORD_ONLY,
        **name_and_dflts,
    ):
        _annotations = _annotations or {}
        names = token_p.findall(_names)
        assert set(names).isdisjoint(
            name_and_dflts
        ), "In order to provide an expected order, we're imposing that _names and **name_and_dflts be disjoint"
        name_and_dflts.update(dict.fromkeys(names, _dflt_default))
        self._dflt_default = _dflt_default
        self._kind = _kind

        if hasattr(self, '__annotations__'):
            self.__annotations__.update(_annotations)
        else:
            self.__annotations__ = _annotations

        reserved = {
            '_annotations',
            '_names',
            '_dflt_default',
            'from_func',
            '_extract_params',
            '_to_signature',
            '_kind',
            'to_parameter_obj_list',
        }
        _name_and_dflts = {
            k: v
            for k, v in self.__class__.__dict__.items()
            if not k.startswith('__') and k not in reserved
        }
        _name_and_dflts.update(name_and_dflts or {})
        self._name_and_dflts = _name_and_dflts

        annots = set(getattr(self, '__annotations__', {}))
        annots |= set(getattr(self.__class__, '__annotations__', {}))

        _reserved = reserved.intersection(set(_name_and_dflts) | set(annots))
        if _reserved:
            raise ValueError(f'Sorry, {_reserved} are reserved names')

    @classmethod
    def from_func(cls, func, _dflt_default=None):
        params = list(signature(func).parameters.values())
        _annotations = {
            x.name: x.annotation for x in params if x.annotation is not Parameter.empty
        }
        _name_and_dflts = dict()
        for x in params:
            dflt = x.default
            if dflt is Parameter.empty:
                dflt = _dflt_default
            _name_and_dflts.update({x.name: dflt})
        _name_and_dflts = {
            x.name: x.default if x.default is not Parameter.empty else _dflt_default
            for x in params
        }
        return cls(
            _annotations=_annotations, _dflt_default=_dflt_default, **_name_and_dflts,
        )

    def _extract_params(self):
        _name_and_dflts = self._name_and_dflts
        annots = getattr(self, '__annotations__', {})
        for name in set(annots) - set(_name_and_dflts):  # annots_not_in_attrs
            yield dict(
                name=name,
                kind=self._kind,
                default=self._dflt_default,
                annotation=annots[name],
            )
        for name, default in _name_and_dflts.items():
            d = dict(name=name, kind=self._kind, default=default)
            if name in annots:
                d.update(annotation=annots[name])
            yield d

    def to_parameter_obj_list(self):
        return list(Parameter(**p) for p in self())

    def _to_signature(self):
        return Signature(Parameter(**p) for p in self())

    def __call__(self):
        return list(self._extract_params())

    def __repr__(self):
        return f'{self()}'


class Decora(Decorator):
    """ A version of Decorator where you can define your subclasses by defininig attributes
    of the subclass (instead of writing a manual __new__ method).

    Here's a typical use, as a decorator factory...

    >>> from py2http.decorators import Decora, ParamsSpecifier
    >>>
    >>>
    >>> class whatevs(ParamsSpecifier):
    ...     minus = 3
    ...     times: float
    ...     repeat: int = 2
    >>>
    >>> class Deco(Decora):
    ...     my_params = whatevs()
    ...
    ...     def __call__(self, *args, **kwargs):
    ...         func_result = super().__call__(*args, **kwargs)
    ...         return func_result[0], [func_result[1] * self.times - self.minus] * self.repeat
    >>>
    >>> def f(w: float, x: int=0, greet='hi'):
    ...     return greet, w + x
    >>>
    >>>
    >>>
    >>> g = Deco(times=3)(f)
    >>> assert g(0) == ('hi', [-3] * 2)
    >>> assert g(10) == ('hi', [27] * 2)
    >>> assert g(10, x=1, greet='hello') == ('hello', [30, 30])
    >>>
    >>> g = Deco(f, times=1, minus=2, repeat=3)
    >>> assert g(0) == ('hi', [-2, -2, -2])
    >>> g = Deco(times=0, minus=3, repeat=1)(f)
    >>> assert g(10) == ('hi', [-3])
    >>> g = Deco(times=2, minus=0, repeat=1)(f)
    >>> assert g(10) == ('hi', [20])
    >>> f = lambda x, y=1: x + y
    >>> f(10)
    11
    >>> signature(f)
    <Signature (x, y=1)>
    >>>

    More examples (of different forms)

    >>> class LogCalls(Decora):
    ...     class DecoParams(ParamsSpecifier):
    ...         verb: str = 'calling'  # will be taken and included in the __init__
    ...         decoy = None  # will be taken (but not actually used in __call__)
    ...
    ...     def __call__(self, *args, **kwargs):
    ...         print(f'{self.verb} {self.func.__name__} with {args} and {kwargs}')
    ...         return super().__call__(*args, **kwargs)
    ...
    >>> ff = LogCalls(f, verb='launching')  # doing it the "decorator way"
    >>> assert ff(10) == 11
    launching <lambda> with (10,) and {}
    >>> signature(ff)
    <Signature (x, y=1)>
    >>> assert signature(ff) == signature(f)  # asserting same signature as the wrapped f
    >>> signature(LogCalls)  # the signature of the decorator itself
    <Signature (func=None, *, verb: str = 'calling', decoy=None)>
    >>>
    >>> ff = LogCalls()(f)  # defaults work when using as factory
    >>> signature(ff)
    <Signature (x, y=1)>
    >>> ff(10)
    calling <lambda> with (10,) and {}
    11
    >>> ff = LogCalls(f)  # defaults work when using as decorator
    >>> ff(10)
    calling <lambda> with (10,) and {}
    11
    >>>
    >>> LogCalls(f, real_arg=False)  # rejects arguments that weren't "registered" by the __new__
    Traceback (most recent call last):
        ...
    TypeError: TypeError: __new__() got unexpected keyword arguments: {'real_arg'}
    >>>

    But you can still do it with __new__ if you want

    >>> class ProcessOutput(Decora):
    ...     def __new__(cls, func=None, *, postproc=None):
    ...         postproc = postproc or (lambda x: x)
    ...         return super().__new__(cls, func, postproc=postproc)
    ...
    ...     def __call__(self, *args, **kwargs):
    ...         return self.postproc(super().__call__(*args, **kwargs))
    ...
    >>> fff = ProcessOutput(postproc=str)(f)  # doing it the "decorator factory way"
    >>> assert fff(10) == "11"
    >>> assert signature(fff)  == signature(f)
    >>> signature(ProcessOutput)  # the signature of the decorator itself
    <Signature (func=None, *, postproc=None)>
    >>>
    >>> # Verifying that LogCalls still has the right signature
    >>> signature(LogCalls)  # the signature of the decorator itself
    <Signature (func=None, *, verb: str = 'calling', decoy=None)>

    """

    _injected_deco_params = ()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if (
            '__new__' not in cls.__dict__
        ):  # if __new__ hasn't been defined in the subclass...
            params = []
            # cls_annots = getattr(cls, '__annotations__', {})
            # injected_deco_params = set()
            for attr_name, attr_obj in cls.__dict__.items():
                setattr(cls, attr_name, attr_obj)
                if isinstance(attr_obj, type) and issubclass(attr_obj, ParamsSpecifier):
                    attr_obj = attr_obj()
                if isinstance(attr_obj, ParamsSpecifier):
                    params.extend(attr_obj.to_parameter_obj_list())

            for p in params:
                setattr(cls, p.name, p.default)
            params = [
                Parameter('self', PK),
                Parameter('func', PK, default=None),
            ] + params
            cls._injected_deco_params = [p.name for p in params]

            def __new__(cls, func=None, **kwargs):
                if cls._injected_deco_params and not set(kwargs).issubset(
                    cls._injected_deco_params
                ):
                    raise TypeError(
                        'TypeError: __new__() got unexpected keyword arguments: '
                        f'{kwargs.keys() - cls._injected_deco_params}'
                    )
                if func is None:
                    return partial(cls, **kwargs)
                else:
                    return Decorator.__new__(cls, func, **kwargs)

            __new__.__signature__ = Signature(params)
            cls.__new__ = __new__


from i2.signatures import copy_func, params_of


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
                    target = copy_func(
                        target
                    )  # make a copy of the function so we don't
                target.__signature__ = Signature(
                    new_params, return_annotation=signature(target).return_annotation,
                )
                return target
            else:
                return new_params
        else:
            return target


def params_replacer(
    replace: Union[dict, Callable[[Parameter], dict]], obj: Iterable[Parameter]
):
    """Generator of transformed params."""

    if isinstance(replace, dict):
        replace = lambda x: replace  # use the same replace on all parameters

    for p in params_of(obj):
        p = p.replace(**(replace(p) or {}))
        yield p


# TODO: generalize instance_attrs to instance_params
# TODO: Use i2.double_up_as_factory?
# TODO: Consider i2.wrapper methodizer
def methodizer(func=None, *, instance_params=()):
    """A decorator to get method versions of functions.

    :param func:
    :param instance_params:
    :return:

    >>> from py2http.decorators import methodizer
    >>>
    >>>
    >>> def f(a, b, x):
    ...     return x * (a + b)
    ...
    >>> def g(x, y=1):
    ...     return x * y
    ...
    >>> methodize = methodizer(instance_params=('x', 'non_existing_attr'))
    >>>
    >>> class A:
    ...     def __init__(self, x=0):
    ...         self.x = x
    ...
    ...     f = methodize(f)
    ...     g = methodize(g)
    ...
    >>>
    >>> a = A(x=3)
    >>> assert a.f(b=1, a=2) == 9
    >>> assert a.g() == 3
    >>> assert a.g(y=10) == 30

    """
    if func is None:
        return partial(methodizer, instance_params=instance_params)
    else:
        func = ch_func_to_all_pk(func)
        func_param_keys = signature(func).parameters.keys()
        self_argnames = func_param_keys & instance_params
        method_argnames = func_param_keys - self_argnames

        def method(self, **kwargs):
            kwargs_from_self = {a: getattr(self, a) for a in self_argnames}
            kwargs.update(kwargs_from_self)
            return func(**kwargs)

        set_signature_of_func(method, ['self'] + list(method_argnames))

        method.__name__ = func.__name__

        return method


from warnings import warn


def _handle_exisisting_method_name(cls, method, if_method_exists):
    if hasattr(cls, method.__name__):
        msg = f'{cls} already has a method named {method.__name__}'
        if if_method_exists == 'raise':
            raise ValueError(msg)
        elif if_method_exists == 'warn':
            warn(msg + ' ... Will overwrite anyway.')
        elif if_method_exists != 'ignore':
            raise ValueError(
                f'if_method_exists value not recognized: {if_method_exists}'
            )


# TODO: inject_methodized_funcs not working yet
#   - signatures have different orders every time (need to use ordered containers)
#   - Values not computed correctly
def inject_methodized_funcs(
    cls=None, *, funcs=(), instance_params=None, if_method_exists='raise'
):
    """

    :param cls:
    :param funcs:
    :param instance_params:
    :param if_method_exists:
    :return:

    # TODO: Come back to inject_methodized_funcs doctest once inject_methodized_funcs is well written
    # >>> from inspect import signature
    # >>>
    # >>>
    # >>> def f(a, b, x):
    # ...     return x * (a + b)
    # ...
    # >>> def g(x, y=1):
    # ...     return x * y
    # ...
    # >>>
    # >>> def h(a, x, c, **kwargs):
    # ...     return f"{a}-{x}-{c}: {list(kwargs.keys())}"
    # ...
    # >>> @inject_methodized_funcs(funcs=(f, g, h))
    # ... class C:
    # ...     def __init__(self, x, a=0, bob=True):
    # ...         self.x = x
    # ...         self.a = a
    # ...         self.bob = bob
    # ...
    # >>>
    # >>>
    # >>> c = C(x=10)
    # >>> for m in ('f', 'g', 'h'):
    # ...     print(f"{C.__name__}.{m}{signature(getattr(c, m))}")
    # ...
    # C.f(b, x)
    # C.g(y, x)
    # C.h(kwargs, c, x)
    """
    raise NotImplementedError('Not working yet: Come back to it!')
    if cls is None:
        return partial(
            inject_methodized_funcs,
            funcs=funcs,
            instance_params=instance_params,
            if_method_exists=if_method_exists,
        )
    else:
        if instance_params is None:
            instance_params = [
                x.name for x in list(signature(cls).parameters.values())[1:]
            ]
        methodize = methodizer(instance_params=instance_params)
        for method in map(methodize, funcs):
            _handle_exisisting_method_name(cls, method, if_method_exists)
            setattr(cls, method.__name__, method)
        return cls


# TODO: Finish this function
def flatten_callables(*callables, func_name=None):
    """
    Flatten a pipeline of calls into one function.
    """
    raise NotImplementedError('Meant to be a generalization of mk_flat')
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


@lru_cache()
def _instantiate(cls, *, cache_id, **kwargs):
    del cache_id  # to emphasize we don't use it and to shut pylint up
    return cls(**kwargs)


# TODO: signature of flat function doesn't reflect actual call restrictions
# TODO: Change default func_name to be dynamically, taking method as default
def mk_flat(cls, method, *, func_name: str = 'flat_func', cls_cache_key: str = None):
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
    :param cls_cache_key: The name of the kwarg used to manage cache. If not None, the
    same instance of ``cls`` will be used for all the flattened method called with the same
    value for this kwarg.
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
    >>> help(f)  # doctest: +SKIP
    Help on function my_special_func in module ...
    <BLANKLINE>
    my_special_func(x, y: float = 1) -> float
    <BLANKLINE>
    >>> f = mk_flat(MultiplierClass, MultiplierClass.subtract)
    >>> help(f)  # doctest: +SKIP
    Help on function flat_func in in module ...
    <BLANKLINE>
    flat_func(x, z)
    <BLANKLINE>
    """
    # sig1 = signature(cls)
    # if isinstance(method, str):
    #     method = getattr(cls, method)
    # sig2 = signature(method)
    # parameters = list(sig1.parameters.values()) + list(sig2.parameters.values())[1:]
    # parameters.sort(key=lambda x: x.kind)  # sort by kind
    # duplicates = [x for x, count in collections.Counter(parameters).items() if count > 1]
    # for d in duplicates:
    #     if d.kind != Parameter.VAR_POSITIONAL and d.kind != Parameter.VAR_KEYWORD:
    #         raise TypeError(
    #             f"Cannot flatten {method.__name__}! Duplicate argument found: {d.name} is in both {cls.__name__} class' and {method.__name__} method's signatures.")
    # parameters = list(dict.fromkeys(parameters))  # remove args and kwargs duplicates

    if isinstance(method, str):
        method = getattr(cls, method)
    sig_cls = Sig(cls)
    sig_method = Sig(method)
    sig_flat = sig_cls + sig_method
    if cls_cache_key:
        param = dict(name=cls_cache_key, kind=KO, default=None)
        sig_flat = sig_flat.add_params([param])
    sig_flat = sig_flat.remove_names(['self'])
    sig_flat = sig_flat.replace(return_annotation=sig_method.return_annotation)

    def flat_func(**kwargs):
        if (
            len(
                [
                    p
                    for p in sig_cls.parameters.values()
                    if p.kind == Parameter.VAR_KEYWORD
                ]
            )
            == 1
        ):
            cls_params = kwargs
        else:
            cls_params = {k: kwargs[k] for k in kwargs if k in sig_cls.parameters}
        if (
            len(
                [
                    p
                    for p in sig_method.parameters.values()
                    if p.kind == Parameter.VAR_KEYWORD
                ]
            )
            == 1
        ):
            method_params = kwargs
        else:
            method_params = {k: kwargs[k] for k in kwargs if k in sig_method.parameters}
        cls_cache_id = next(
            iter(v for k, v in kwargs.items() if k == cls_cache_key), None
        )
        if cls_cache_id is not None:
            instance = _instantiate(cls, cache_id=cls_cache_id, **cls_params)
        else:
            instance = cls(**cls_params)
        return getattr(instance, method.__name__)(**method_params)

    flat_func.__dict__ = method.__dict__.copy()  # to copy attributes of method
    flat_func.__signature__ = sig_flat
    flat_func.__name__ = func_name
    flat_func.__doc__ = method.__doc__

    return flat_func


def flatten_methods(methods: dict, decorator=None, validate_name_unicity=True):
    if not decorator:
        decorator = lambda x: x
    functions = []
    for cls, cls_method_names in methods.items():
        functions.extend(
            [
                decorator(mk_flat(cls, getattr(cls, x), func_name=x))
                for x in cls_method_names
            ]
        )
    if validate_name_unicity:
        nb_function_names = len({x.__name__: x for x in functions})
        if nb_function_names != len(functions):
            raise ValueError(f'Some function names are duplicated in {methods}')
    return functions


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


http_get = add_attrs(http_method='get')
http_post = add_attrs(http_method='post')
http_put = add_attrs(http_method='put')
http_delete = add_attrs(http_method='delete')


def route(route_name):
    return add_attrs(route=route_name)


def _validate_and_invoke_mapper(func, inputs):
    request_schema = getattr(func, 'request_schema', None)
    if request_schema:
        validate_input(inputs, request_schema)
    return func(**inputs)


def _handle_req(func, content_type):
    func.request_schema = mk_input_schema_from_func(func)
    func.content_type = content_type

    # TODO: make this work with Bottle
    @wraps(func)
    def input_mapper(req):
        if content_type not in req.content_type:
            raise RuntimeError(
                f"The incoming request's content is of type \
{req.content_type}, when {content_type} is expected."
            )
        inputs = _get_inputs_from_request(req, content_type)
        return _validate_and_invoke_mapper(func, inputs)

    return input_mapper


def handle_json_req(func):
    return _handle_req(func, JSON_CONTENT_TYPE)


def handle_binary_req(func):
    return _handle_req(func, BINARY_CONTENT_TYPE)


def handle_form_req(func):
    return _handle_req(func, FORM_CONTENT_TYPE)


def handle_raw_req(func):
    return _handle_req(func, RAW_CONTENT_TYPE)


def base_output_mapper(output, **inputs):
    return output


# TODO: Definitely want to move this to a place that is specialized for defining serialization needs
#   First, it's not really a decorator.
#   Secondly, the user should be able to easily define the serialization logic for their needs
#   Thirdly, ObjectId is specific to mongo. No specifics should be here
#   Fourthly, if we do have such specific package-dependent stuffs, we need to condition on existence
class JsonRespEncoder(JSONEncoder):
    def default(self, o):
        with ModuleNotFoundIgnore():  # added this to condition bson existence
            from bson import ObjectId  # added this to condition bson existence

            if isinstance(o, ObjectId):
                return str(o)
        return JSONEncoder.default(self, o)


# See proposal for JsonRespEncoder (understand and expand (and move)) below:


def _mk_default_serializer_for_type():
    _serializer_for_type = {}

    with ModuleNotFoundIgnore():
        from bson import ObjectId

        _serializer_for_type[ObjectId] = str

    return _serializer_for_type


def _json_reponse_preproc(o, serializer_for_type):
    for _type, _serializer in serializer_for_type.items():
        if isinstance(o, _type):
            return o
    return o  # if not returned before


class ProposalJsonRespEncoder(JSONEncoder):
    # Note: Subclass and replace _pre_process_obj to get different preprocessing
    # Note: To get control from init, definte init to set _pre_process_obj
    _pre_process_obj = partial(
        _json_reponse_preproc, serializer_for_type=_mk_default_serializer_for_type(),
    )

    def default(self, o):
        o = self._pre_process_obj(o)
        return JSONEncoder.default(self, o)


def send_json_resp(func):
    framework = os.getenv('PY2HTTP_FRAMEWORK', BOTTLE)
    if framework == AIOHTTP:

        async def output_mapper(output, **input_kwargs):
            mapped_output = func(output, **input_kwargs)
            if isawaitable(mapped_output):
                mapped_output = await mapped_output
            return web.json_response(mapped_output, dumps=JsonRespEncoder().encode)

    else:

        def output_mapper(output, **input_kwargs):
            response.content_type = JSON_CONTENT_TYPE
            mapped_output = func(output, **input_kwargs)
            return dumps(mapped_output, cls=JsonRespEncoder)

    output_mapper.content_type = JSON_CONTENT_TYPE
    return output_mapper


def send_binary_resp(func):
    def output_mapper(output, **input_kwargs):
        response.content_type = BINARY_CONTENT_TYPE
        mapped_output = func(output, **input_kwargs)
        return pickle.dumps(mapped_output)

    output_mapper.content_type = BINARY_CONTENT_TYPE
    output_mapper.response_schema = {'type': 'binary'}
    return output_mapper


def send_raw_resp(func):
    def output_mapper(output, **input_kwargs):
        response.content_type = RAW_CONTENT_TYPE
        return func(output, **input_kwargs)

    output_mapper.content_type = RAW_CONTENT_TYPE
    return output_mapper


def send_html_resp(func):
    # TODO bottle support
    # async def output_mapper(output, **input_kwargs):
    #     mapped_output = func(output, input_kwargs)
    #     if isawaitable(mapped_output):
    #         mapped_output = await mapped_output
    #     return Response(text=mapped_output, content_type='text/html')

    func.content_type = HTML_CONTENT_TYPE
    return func


# def send_form_resp(func):
#     # TODO async support
#     def output_mapper(output, **input_kwargs):
#         response.content_type = FORM_CONTENT_TYPE
#         return func(output, **input_kwargs)

#     output_mapper.content_type = FORM_CONTENT_TYPE
#     output_mapper.response_schema = {'type': 'binary'}
#     return output_mapper


def binary_output(func):
    output_mapper = send_binary_resp(base_output_mapper)
    func.output_mapper = output_mapper
    return func


# TODO: stub
def mk_input_mapper(input_map):
    def decorator(func):
        return func

    return decorator


def _get_inputs_from_request(request, content_type):
    defaults = getattr(request, 'defaults', {})
    if request.method == 'POST':
        if content_type == JSON_CONTENT_TYPE:
            inputs = request.json
        elif content_type == RAW_CONTENT_TYPE:
            data = request.body.read().decode('utf-8')
            inputs = json.loads(data)
        elif content_type == BINARY_CONTENT_TYPE:
            data = request.body.read()
            inputs = pickle.loads(data)
        elif content_type == FORM_CONTENT_TYPE:
            fields = json.loads(
                request.files.pop('__fields').file.read().decode('utf-8')
            )
            binaries = {k: v.file.read() for k, v in request.files.items()}
            inputs = dict(fields, **binaries)
        return dict(defaults, **inputs)
    else:
        raise NotImplementedError('Only POST is supported for now')


def mk_handlers(methods: Iterable, *, decorator=None, cls_cache_key=None):
    def get_class_that_defined_method(meth):
        if inspect.ismethod(meth):
            for cls in inspect.getmro(meth.__self__.__class__):
                if meth.__name__ in cls.__dict__:
                    return cls
            meth = meth.__func__  # fallback to __qualname__ parsing
        if inspect.isfunction(meth):
            cls = getattr(
                inspect.getmodule(meth),
                meth.__qualname__.split('.<locals>', 1)[0].rsplit('.', 1)[0],
                None,
            )
            if isinstance(cls, type):
                sub_classes = cls.__subclasses__()
                if len(sub_classes) == 1:
                    return sub_classes[0]
                return cls
        return None

    if not decorator:
        decorator = lambda x: x
    handlers = []
    for item in methods:
        has_mappers = isinstance(item, dict)
        method = item['endpoint'] if has_mappers else item
        cls = get_class_that_defined_method(method)
        endpoint = decorator(
            mk_flat(cls, method, func_name=method.__name__, cls_cache_key=cls_cache_key)
        )
        handler = dict(item, endpoint=endpoint) if has_mappers else endpoint
        handlers.append(handler)
    return handlers
