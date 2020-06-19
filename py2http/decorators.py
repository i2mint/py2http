from inspect import signature, Signature, Parameter
from typing import Iterable, Callable, Union, Mapping
from functools import partial, wraps, update_wrapper
from json import JSONDecodeError, JSONEncoder
from types import FunctionType
from warnings import warn
from aiohttp import web
from bson import ObjectId

ParameterKind = type(Parameter.POSITIONAL_OR_KEYWORD)  # to get the enum type

Params = Iterable[Parameter]
HasParams = Union[Iterable[Parameter], Mapping[str, Parameter], Signature, Callable]

# short hands for Parameter kinds
PK = Parameter.POSITIONAL_OR_KEYWORD
VP, VK = Parameter.VAR_POSITIONAL, Parameter.VAR_KEYWORD
PO, KO = Parameter.POSITIONAL_ONLY, Parameter.KEYWORD_ONLY
var_param_types = {VP, VK}


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
        setattr(owner, name, DecoParameter(name, self.dflt_param_kind,
                                           default=self.default, annotation=self.annotation))


from typing import Optional
import re

token_p = re.compile('\w+')


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

    def __init__(self,
                 _annotations: Optional[dict] = None,
                 _names: str = '',
                 _dflt_default=None,
                 _kind=Parameter.KEYWORD_ONLY,
                 **name_and_dflts):
        _annotations = _annotations or {}
        names = token_p.findall(_names)
        assert set(names).isdisjoint(name_and_dflts), \
            "In order to provide an expected order, we're imposing that _names and **name_and_dflts be disjoint"
        name_and_dflts.update(dict.fromkeys(names, _dflt_default))
        self._dflt_default = _dflt_default
        self._kind = _kind

        if hasattr(self, '__annotations__'):
            self.__annotations__.update(_annotations)
        else:
            self.__annotations__ = _annotations

        reserved = {'_annotations', '_names', '_dflt_default', 'from_func',
                    '_extract_params', '_to_signature', '_kind', 'to_parameter_obj_list'}
        _name_and_dflts = {k: v for k, v in self.__class__.__dict__.items()
                           if not k.startswith('__') and k not in reserved}
        _name_and_dflts.update(name_and_dflts or {})
        self._name_and_dflts = _name_and_dflts

        annots = set(getattr(self, '__annotations__', {}))
        annots |= set(getattr(self.__class__, '__annotations__', {}))

        _reserved = reserved.intersection(set(_name_and_dflts) | set(annots))
        if _reserved:
            raise ValueError(f"Sorry, {_reserved} are reserved names")

    @classmethod
    def from_func(cls, func, _dflt_default=None):
        params = list(signature(func).parameters.values())
        _annotations = {x.name: x.annotation for x in params if x.annotation is not Parameter.empty}
        _name_and_dflts = dict()
        for x in params:
            dflt = x.default
            if dflt is Parameter.empty:
                dflt = _dflt_default
            _name_and_dflts.update({x.name: dflt})
        _name_and_dflts = {x.name: x.default if x.default is not Parameter.empty else _dflt_default
                           for x in params}
        return cls(_annotations=_annotations, _dflt_default=_dflt_default, **_name_and_dflts)

    def _extract_params(self):
        _name_and_dflts = self._name_and_dflts
        annots = getattr(self, '__annotations__', {})
        for name in (set(annots) - set(_name_and_dflts)):  # annots_not_in_attrs
            yield dict(name=name, kind=self._kind, default=self._dflt_default, annotation=annots[name])
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
        return f"{self()}"


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
        if '__new__' not in cls.__dict__:  # if __new__ hasn't been defined in the subclass...
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
            params = [Parameter('self', PK), Parameter('func', PK, default=None)] + params
            cls._injected_deco_params = [p.name for p in params]

            def __new__(cls, func=None, **kwargs):
                if cls._injected_deco_params and not set(kwargs).issubset(cls._injected_deco_params):
                    raise TypeError("TypeError: __new__() got unexpected keyword arguments: "
                                    f"{kwargs.keys() - cls._injected_deco_params}")
                if func is None:
                    return partial(cls, **kwargs)
                else:
                    return Decorator.__new__(cls, func, **kwargs)

            __new__.__signature__ = Signature(params)
            cls.__new__ = __new__


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
    (x, y=1, args=(), **kwargs)
    """
    func = tuple_the_args(func)
    sig = signature(func)
    func.__signature__ = ch_signature_to_all_pk(sig)
    return func

from py2http.signatures import set_signature_of_func


def methodizer(func=None, *, instance_attrs=()):
    """A decorator to get method versions of functions.

    :param func:
    :param instance_attrs:
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
    >>> methodize = methodizer(instance_attrs=('x', 'non_existing_attr'))
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
        return partial(methodizer, instance_attrs=instance_attrs)
    else:
        func = ch_func_to_all_pk(func)
        func_param_keys = signature(func).parameters.keys()
        self_argnames = func_param_keys & instance_attrs
        method_argnames = func_param_keys - self_argnames

        def method(self, **kwargs):
            kwargs_from_self = {a: getattr(self, a) for a in self_argnames}
            kwargs.update(kwargs_from_self)
            return func(**kwargs)

        set_signature_of_func(method, ['self'] + list(method_argnames))

        method.__name__ = func.__name__

        return method


# TODO: Finish this function
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
        return getattr(instance, method.__name__)(**for2)

    flat_func.__dict__ = method.__dict__.copy()
    flat_func.__signature__ = Signature(parameters, return_annotation=sig2.return_annotation)
    flat_func.__name__ = func_name

    final_sig = signature(flat_func)
    print(f'signature of output function: {final_sig.parameters}')

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


http_get = add_attrs(http_method='get')
http_post = add_attrs(http_method='post')
http_put = add_attrs(http_method='put')
http_delete = add_attrs(http_method='delete')


def route(route_name):
    return add_attrs(route=route_name)


def handle_json_req(func):
    async def input_mapper(req):
        try:
            body = await req.json()
        except JSONDecodeError:
            warn('Invalid req body, expected JSON format.')
            body = {}
        kwargs = _get_req_input_kwargs(req, body)
        return func(kwargs)
    input_mapper.content_type = 'json'
    return input_mapper


def handle_multipart_req(func):
    async def input_mapper(req):
        try:
            body = await req.post()
        except Exception:
            warn('Invalid req body, expected multipart format.')
            body = {}
        kwargs = _get_req_input_kwargs(req, body)
        return func(kwargs)
    input_mapper.content_type = 'multipart'
    return input_mapper


def handle_raw_req(func):
    async def input_mapper(req):
        raw_body = await req.text()
        body = dict({}, text=raw_body)
        kwargs = _get_req_input_kwargs(req, body)
        return func(kwargs)
    input_mapper.content_type = 'raw'
    return input_mapper


def send_json_resp(func):
    class JsonRespEncoder(JSONEncoder):
        def default(self, o):
            if isinstance(o, ObjectId):
                return str(o)
            return JSONEncoder.default(self, o)

    def output_mapper(output, input_kwargs):
        mapped_output = func(output, input_kwargs)
        return web.json_response(mapped_output, dumps=JsonRespEncoder().encode)

    output_mapper.content_type = 'json'
    return output_mapper


def send_html_resp(func):
    def output_mapper(output, input_kwargs):
        mapped_output = func(output, input_kwargs)
        return web.Response(text=mapped_output, content_type='text/html')

    output_mapper.content_type = 'html'
    return output_mapper


# TODO: stub
def mk_input_mapper(input_map):
    def decorator(func):
        return func

    return decorator


def _get_req_input_kwargs(req, body):
    kwargs = body
    if getattr(req, 'query', None):
        kwargs = dict(kwargs, **req.query)
    if getattr(req, 'token', None):
        kwargs = dict(kwargs, **req.token)
    return kwargs
