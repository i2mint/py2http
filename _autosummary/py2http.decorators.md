# py2http.decorators

Decorator tools for py2http.

### Functions

| [`add_attrs`](#py2http.decorators.add_attrs)(\*\*attrs)                           | Makes a function that adds attributes to a function.                        |
|-------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------|
| `base_output_mapper`(output, \*\*inputs)                                                        |                                                                             |
| `binary_output`(func)                                                                           |                                                                             |
| [`ensure_awaitable_return_annot`](#py2http.decorators.ensure_awaitable_return_annot)(func)            |                                                                             |
| [`flatten_callables`](#py2http.decorators.flatten_callables)(\*callables[, func_name])    | Flatten a pipeline of calls into one function.                              |
| `flatten_methods`(methods[, decorator, ...])                                                    |                                                                             |
| `handle_binary_req`(func)                                                                       |                                                                             |
| `handle_form_req`(func)                                                                         |                                                                             |
| `handle_json_req`(func)                                                                         |                                                                             |
| `handle_raw_req`(func)                                                                          |                                                                             |
| `http_delete`(func)                                                                             |                                                                             |
| `http_get`(func)                                                                                |                                                                             |
| `http_post`(func)                                                                               |                                                                             |
| `http_put`(func)                                                                                |                                                                             |
| `ignore_extra_arguments`(func)                                                                  |                                                                             |
| [`inject_methodized_funcs`](#py2http.decorators.inject_methodized_funcs)([cls, funcs, ...])     |                                                                             |
| [`methodizer`](#py2http.decorators.methodizer)([func, instance_params])            | A decorator to get method versions of functions.                            |
| [`mk_flat`](#py2http.decorators.mk_flat)(cls, method, \*[, func_name, ...])     | Flatten a simple cls->instance->method call pipeline into one function.     |
| `mk_handlers`(methods, \*[, decorator, ...])                                                    |                                                                             |
| `mk_input_mapper`(input_map)                                                                    |                                                                             |
| [`params_replacer`](#py2http.decorators.params_replacer)(replace, obj)                  | Generator of transformed params.                                            |
| [`replace_with_params`](#py2http.decorators.replace_with_params)([target, source, inplace]) | Will return a version of the target type that has params taken from source. |
| `route`(route_name)                                                                             |                                                                             |
| `send_binary_resp`(func)                                                                        |                                                                             |
| `send_html_resp`(func)                                                                          |                                                                             |
| `send_json_resp`(func)                                                                          |                                                                             |
| `send_raw_resp`(func)                                                                           |                                                                             |

### Classes

| `DecoParam`(default, annotation)                                                                    |                                                                                                                                                      |
|-----------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`DecoParameter`](#py2http.decorators.DecoParameter)(name, kind, \*, default, annotation) | A Parameter object that is meant to be the a parameter of a decorator factory.                                                                       |
| [`Decora`](#py2http.decorators.Decora)([func])                                     | A version of Decorator where you can define your subclasses by defininig attributes of the subclass (instead of writing a manual \_\_new_\_ method). |
| [`Decorator`](#py2http.decorators.Decorator)([func])                                  | A "transparent" decorator meant to be used to subclass into specialized decorators.                                                                  |
| [`JsonRespEncoder`](#py2http.decorators.JsonRespEncoder)(\*[, skipkeys, ensure_ascii, ...]) |                                                                                                                                                      |
| [`Literal`](#py2http.decorators.Literal)(val)                                       | An object to indicate that the value should be considered literally                                                                                  |
| [`ParamsSpecifier`](#py2http.decorators.ParamsSpecifier)([_annotations, \_names, ...])      | A tool to specify params (that is, lists of inspect.Parameter instances that are used in callable signatures.                                        |
| [`ProposalJsonRespEncoder`](#py2http.decorators.ProposalJsonRespEncoder)(\*[, skipkeys, ...])       |                                                                                                                                                      |

### *class* py2http.decorators.DecoParameter(name, kind, , default, annotation)

Bases: [`Parameter`](https://docs.python.org/3/library/inspect.html#inspect.Parameter)

A Parameter object that is meant to be the a parameter of a decorator factory.
Subclassing inspect.Parameter so that it can be distinguished from it if needed.

### *class* py2http.decorators.Decora(func=None, \*\*kwargs)

Bases: [`Decorator`](#py2http.decorators.Decorator)

A version of Decorator where you can define your subclasses by defininig attributes
of the subclass (instead of writing a manual \_\_new_\_ method).

Here’s a typical use, as a decorator factory…

```pycon
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
```

More examples (of different forms)

```pycon
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
```

But you can still do it with \_\_new_\_ if you want

```pycon
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
```

### *class* py2http.decorators.Decorator(func=None, \*\*kwargs)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A “transparent” decorator meant to be used to subclass into specialized decorators.

The signature of the wrapped function is carried to the \_\_call_\_ of the decorated instance.

To specialize (and do something else than just “transparent” wrapping, you need to subclass
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
For example: If you want to have a proper signature (not just \*\*kwargs),
you need to overwrite `__new__` for the sole purpose of specifying the arguments
(names, and optional annotations and defaults).
This problem is not taken care of here, but you can check out `Decora`,
a subclass of Decorator, that does.

```pycon
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
>>> # rejects arguments that weren't "registered" by the __new__:
>>> LogCalls(f, real_arg=False)
Traceback (most recent call last):
    ...
TypeError: __new__() got an unexpected keyword argument 'real_arg'
```

### *class* py2http.decorators.JsonRespEncoder(, skipkeys=False, ensure_ascii=True, check_circular=True, allow_nan=True, sort_keys=False, indent=None, separators=None, default=None)

Bases: [`JSONEncoder`](https://docs.python.org/3/library/json.html#json.JSONEncoder)

#### default(o)

Implement this method in a subclass such that it returns
a serializable object for `o`, or calls the base implementation
(to raise a `TypeError`).

For example, to support arbitrary iterators, you could
implement default like this:

```default
def default(self, o):
    try:
        iterable = iter(o)
    except TypeError:
        pass
    else:
        return list(iterable)
    # Let the base class default method raise the TypeError
    return super().default(o)
```

### *class* py2http.decorators.Literal(val)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

An object to indicate that the value should be considered literally

### *class* py2http.decorators.ParamsSpecifier(\_annotations=None, \_names='', \_dflt_default=None, \_kind=\_ParameterKind.KEYWORD_ONLY, \*\*name_and_dflts)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A tool to specify params (that is, lists of inspect.Parameter instances that
are used in callable signatures.

But wait! you may not need this!

Often the cleanest way to make a signature, or list of Parameters is to define an empty function
with that signature, and extract it from there.

See `Decora` for the original intended use of ParamsSpecifier.

```pycon
>>> from inspect import signature, Signature, Parameter
>>> def f(a, b: int, c: float = 0.0, d: str='hi'): ...
>>> sig = signature(f)
>>> sig
<Signature (a, b: int, c: float = 0.0, d: str = 'hi')>
>>> list(sig.parameters.values())
[<Parameter "a">, <Parameter "b: int">, <Parameter "c: float = 0.0">, <Parameter "d: str = 'hi'">]
```

The reason for the existence of ParamsSpecifier was to do some magic around giving class-based
decorators a signature. The reasons of this magic may be outdated soon.

```pycon
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
```

See that the params are all valid kwargs to inspect.Parameter, by making a signature from them

```pycon
>>> Signature(Parameter(**p) for p in params)
<Signature (*, z: float = None, b=3, c: int = 2)>
```

Let’s now get another params specifier.

```pycon
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
```

One thing to note in the expected_params is the order.
Indeed, the order is not the order that is taken (because couldn’t figure out otherwise)
is as such:

- First the class-level attributes that are annotated, but not given a default
  : (though a blanket \_dflt_default default will be given to them all).
    Here order is not assured.
- Second the reset of the class-level attributes, in the order they were defined.
- Third the instance argument params given by the \_names argument, in the order they were listed.
- Finally the instance argument name_and_dflts params, in the order they were listed.

Remember, all this is meant to provide ways to specify signatures.

```pycon
>>> Signature(Parameter(**p) for p in params)
<Signature (*, z: float = None, b: int = 3, c: int = 2, another='here', a: str = None, wol=None)>
```

Now, not that ParamsSpecifier is the tool for this, but to demo what ParamsSpecifier’s
params are, we’ll give one last example where we take a function, make a ParamsSpecifier
from it, and add a different kind of default

```pycon
>>> def f(a, b: int, c: float = 0.0, d: str='hi'): ...
>>> param_maker = ParamsSpecifier.from_func(f, _dflt_default='a different dflt')
>>> Signature(Parameter(**p) for p in param_maker())
<Signature (*, a='a different dflt', b: int = 'a different dflt', c: float = 0.0, d: str = 'hi')>
```

### *class* py2http.decorators.ProposalJsonRespEncoder(, skipkeys=False, ensure_ascii=True, check_circular=True, allow_nan=True, sort_keys=False, indent=None, separators=None, default=None)

Bases: [`JSONEncoder`](https://docs.python.org/3/library/json.html#json.JSONEncoder)

#### default(o)

Implement this method in a subclass such that it returns
a serializable object for `o`, or calls the base implementation
(to raise a `TypeError`).

For example, to support arbitrary iterators, you could
implement default like this:

```default
def default(self, o):
    try:
        iterable = iter(o)
    except TypeError:
        pass
    else:
        return list(iterable)
    # Let the base class default method raise the TypeError
    return super().default(o)
```

### py2http.decorators.add_attrs(\*\*attrs)

Makes a function that adds attributes to a function.

Used in it’s normal context, it looks something like this:

```pycon
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
```

But it can be useful to make attribute adder, and reuse when needed.

```pycon
>>> brand_my_func = add_attrs(author="me")
>>> _ = brand_my_func(foo)  # not capturing the output to show that the change happens in-place
>>> foo.author
'me'
```

### py2http.decorators.ensure_awaitable_return_annot(func)

```pycon
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
```

### py2http.decorators.flatten_callables(\*callables, func_name=None)

Flatten a pipeline of calls into one function.

### py2http.decorators.inject_methodized_funcs(cls=None, , funcs=(), instance_params=None, if_method_exists='raise')

* **Parameters:**
  * **cls**
  * **funcs**
  * **instance_params**
  * **if_method_exists**
* **Returns:**

# TODO: Come back to inject_methodized_funcs doctest once inject_methodized_funcs is well written
# >>> from inspect import signature
# >>>
# >>>
# >>> def f(a, b, x):
# …     return x \* (a + b)
# …
# >>> def g(x, y=1):
# …     return x \* y
# …
# >>>
# >>> def h(a, x, c, \*\*kwargs):
# …     return f”{a}-{x}-{c}: {list(kwargs.keys())}”
# …
# >>> @inject_methodized_funcs(funcs=(f, g, h))
# … class C:
# …     def \_\_init_\_(self, x, a=0, bob=True):
# …         self.x = x
# …         self.a = a
# …         self.bob = bob
# …
# >>>
# >>>
# >>> c = C(x=10)
# >>> for m in (‘f’, ‘g’, ‘h’):
# …     print(f”{C._\_name_\_}.{m}{signature(getattr(c, m))}”)
# …
# C.f(b, x)
# C.g(y, x)
# C.h(kwargs, c, x)

### py2http.decorators.methodizer(func=None, , instance_params=())

A decorator to get method versions of functions.

* **Parameters:**
  * **func**
  * **instance_params**
* **Returns:**

```pycon
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
```

### py2http.decorators.mk_flat(cls, method, , func_name='flat_func', cls_cache_key=None)

Flatten a simple cls->instance->method call pipeline into one function.

That is, a function mk_flat(cls, method) that returns a “flat function” such that

```text
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

* **Parameters:**
  * **cls** – A class
  * **method** – A method of this class
  * **func_name** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The name of the function (will be “flat_func” by default)
  * **cls_cache_key** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – The name of the kwarg used to manage cache. If not None, the
    same instance of `cls` will be used for all the flattened method called with the same
    value for this kwarg.
* **Returns:**

```pycon
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
Help on function my_special_func in module ...

my_special_func(x, y: float = 1) -> float

>>> f = mk_flat(MultiplierClass, MultiplierClass.subtract)
>>> help(f)
Help on function flat_func in in module ...

flat_func(x, z)
```

### py2http.decorators.params_replacer(replace, obj)

Generator of transformed params.

### py2http.decorators.replace_with_params(target=None, , , source=None, inplace=False)

Will return a version of the target type that has params taken from source.
Both target and source can be of the HasParams type, i.e.

```text
Union[Iterable[Parameter], Mapping[str, Parameter], Signature, Callable]
```

```pycon
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
```
