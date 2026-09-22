# py2http.util

This module contains various utilities including a `lazyprop` descriptor for lazy loading properties, a `CreateProcess` context manager for running functions in parallel processes, a `ModuleFoundIgnore` context manager for ignoring `ModuleNotFoundErrors`, and more.

The `lazyprop` descriptor is used to define properties that are computed once and then cached until the instance of the class is destroyed. It is useful for computing properties on-demand but only once.

The `CreateProcess` context manager is used to launch a parallel process and close it on exit. This is helpful when you need to execute tasks concurrently in a separate process.

The `ModuleFoundIgnore` context manager allows you to ignore `ModuleNotFoundError` exceptions in a block of code. This can be useful when importing optional modules that may or may not exist.

The `TypeAsserter` function generates a callable that asserts the expected type of a value based on a given kind. It can be used to validate the types of inputs based on predefined rules.

Overall, this module provides a collection of useful tools for handling lazy property loading, parallel processing, exception handling, type validation, and more.

### Functions

| `conditional_logger`([verbose, log_func])                                            |                                                                                                             |
|--------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------|
| [`deprecate`](#py2http.util.deprecate)([func, msg])              | Decorator to emit a DeprecationWarning when the decorated function is called.                               |
| `if_not_empty`(obj[, if_empty_val])                                                  |                                                                                                             |
| [`obj_to_items_gen`](#py2http.util.obj_to_items_gen)(obj, attrs[, ...]) | Make a generator of (k, v) items extracted from an input object, given an iterable of attributes to extract |
| [`obj_to_path`](#py2http.util.obj_to_path)(obj)                    | Quasi-inverse of obj_to_path: Get a root_obj and attr_path from an object.                                  |
| [`path_to_obj`](#py2http.util.path_to_obj)(root_obj, attr_path)    | Get an object from a root object and "attribute path" specification.                                        |
| `py_obj_info`(obj)                                                                   |                                                                                                             |
| [`pyparam_to_dict`](#py2http.util.pyparam_to_dict)(param[, kv_trans])  | Get dict from a Parameter object                                                                            |

### Classes

| [`CreateProcess`](#py2http.util.CreateProcess)(proc_func[, process_name, ...])   | A context manager to launch a parallel process and close it on exit.                                 |
|--------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------|
| [`Missing`](#py2http.util.Missing)([val])                                  | A class to use as a value to indicate that something was missing                                     |
| [`ModuleNotFoundIgnore`](#py2http.util.ModuleNotFoundIgnore)()                          | Context manager to ignore ModuleNotFoundErrors.                                                      |
| [`Skip`](#py2http.util.Skip)()                                          | Class to indicate if one should skip an item                                                         |
| [`TypeAsserter`](#py2http.util.TypeAsserter)(types_for_kind[, if_kind_missing]) | Makes a callable that asserts that a value `v` has the expected type(s) that it's kind `k` should be |
| [`lazyprop`](#py2http.util.lazyprop)(func)                                  | A descriptor implementation of lazyprop (cached property).                                           |

### *class* py2http.util.CreateProcess(proc_func, process_name=None, wait_before_entering=2, verbose=False, args=(), \*\*kwargs)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A context manager to launch a parallel process and close it on exit.

### *class* py2http.util.Missing(val=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A class to use as a value to indicate that something was missing

### *class* py2http.util.ModuleNotFoundIgnore

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Context manager to ignore ModuleNotFoundErrors.

When all goes well, code is executed normally:

```pycon
>>> with ModuleNotFoundIgnore():
...     import os.path  # test when the module exists
...     # The following code is reached and executed
...     print('hi there!')
...     print(str(os.path.join)[:14] + '...')  # code is reached
hi there!
<function join...
```

But if you try to import a module that doesn’t exist on your system,
the block will be skipped from that point onward, silently.

```pycon
>>> with ModuleNotFoundIgnore():
...     import do.i.exist
...     # The following code is NEVER reached or executed
...     print(do.i.exist)
...     t = 0 / 0
```

But if there’s any other kind of error (other than ModuleNotFoundError that is,
the error will be raised normally.

```pycon
>>> with ModuleNotFoundIgnore():
...     t = 0/0
Traceback (most recent call last):
  ...
ZeroDivisionError: division by zero
```

### *class* py2http.util.Skip

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Class to indicate if one should skip an item

### *class* py2http.util.TypeAsserter(types_for_kind, if_kind_missing='ignore')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Makes a callable that asserts that a value `v` has the expected type(s) that it’s kind `k` should be

```pycon
>>> assert_type = TypeAsserter({'foo': str, 'bar': (Callable, type(None))})
>>> assert_type('bar', lambda x: x)
>>> assert_type('bar', None)
>>> assert_type('foo', 'i am a string')
>>> assert_type('foo', list('i am not a string'))
Traceback (most recent call last):
  ...
AssertionError: Invalid foo type, must be a <class 'str'>, but was a <class 'list'>
```

If a kind wasn’t specified, the default is to ignore

```pycon
>>> assert_type('not_a_kind', 'blah')
>>> assert_type = TypeAsserter({'foo': str, 'bar': (Callable, type(None))})  # nothing happens
```

But you can choose to warn or raise an exception instead

```pycon
>>> assert_type = TypeAsserter({'foo': str, 'bar': list}, if_kind_missing='raise')
>>> assert_type('not_a_kind', 'blah')
Traceback (most recent call last):
    ...
ValueError: Unrecognized kind: not_a_kind. The ones I recognize: ['foo', 'bar']
```

### py2http.util.deprecate(func=None, , msg=None)

Decorator to emit a DeprecationWarning when the decorated function is called.

### *class* py2http.util.lazyprop(func)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A descriptor implementation of lazyprop (cached property).
Made based on David Beazley’s “Python Cookbook” book and enhanced with boltons.cacheutils ideas.

```pycon
>>> class Test:
...     def __init__(self, a):
...         self.a = a
...     @lazyprop
...     def len(self):
...         print('generating "len"')
...         return len(self.a)
>>> t = Test([0, 1, 2, 3, 4])
>>> t.__dict__
{'a': [0, 1, 2, 3, 4]}
>>> t.len
generating "len"
5
>>> t.__dict__
{'a': [0, 1, 2, 3, 4], 'len': 5}
>>> t.len
5
>>> # But careful when using lazyprop that no one will change the value of a without deleting the property first
>>> t.a = [0, 1, 2]  # if we change a...
>>> t.len  # ... we still get the old cached value of len
5
>>> del t.len  # if we delete the len prop
>>> t.len  # ... then len being recomputed again
generating "len"
3
```

### py2http.util.obj_to_items_gen(obj, attrs, on_missing_attr=<class 'py2http.util.Missing'>, kv_trans=<function <lambda>>)

Make a generator of (k, v) items extracted from an input object, given an iterable of attributes to extract

* **Parameters:**
  * **obj** – A python object
  * **attrs** ([`Iterable`](https://docs.python.org/3/library/typing.html#typing.Iterable)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – The iterable of attributes to extract from obj
  * **on_missing_val** – 

    What to do if an attribute is missing:
    - Skip: Skip the item
    - Callable: Call a function with the attribute as an input
    - anything else: Just return that as a value
  * **kv_trans** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)])
* **Returns:**
  A generator

### py2http.util.obj_to_path(obj)

Quasi-inverse of obj_to_path: Get a root_obj and attr_path from an object.
Obviously, would only be able to work with some types (only by-ref types?).

```pycon
>>> class A:
...     def foo(self, x): ...
...     foo.x = 3
...     class B:
...         def bar(self, x): ...
...
>>> for t in [(A, ('foo',)), (A, ('B',)), (A, ('B', 'bar'))]:
...     print(obj_to_path(path_to_obj(*t)))
...     print(t)
...     print()
(<class 'util.A'>, ('foo',))
(<class 'util.A'>, ('foo',))

<class 'util.A.B'>
(<class 'util.A'>, ('B',))

(<class 'util.A'>, ('B', 'bar'))
(<class 'util.A'>, ('B', 'bar'))
```

# >>> for t in [(A, (‘foo’,)), (A, (‘B’,)), (A, (‘B’, ‘bar’))]:
# …     assert obj_to_path(path_to_obj(\*t)) == t

### py2http.util.path_to_obj(root_obj, attr_path)

Get an object from a root object and “attribute path” specification.

```pycon
>>> class A:
...     def foo(self, x): ...
...     foo.x = 3
...     class B:
...         def bar(self, x): ...
...
>>> obj = path_to_obj(A, ('foo',))
>>> assert callable(obj) and obj.__name__ == 'foo'
>>> path_to_obj(A, ('foo', 'x'))
3
>>> obj = path_to_obj(A, ('B', 'bar'))
>>> assert callable(obj) and obj.__qualname__ == 'A.B.bar'
```

### py2http.util.pyparam_to_dict(param, kv_trans=<function \_pyparam_kv_trans.skip_empties>)

Get dict from a Parameter object

* **Parameters:**
  * **param** – A inspect.Parameter instance
  * **kv_trans** ([`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)) – A callable that will be called on the (k, v) attribute items of the Parameter instance
* **Returns:**
  A dict extracted from this Parameter

```pycon
>>> from inspect import Parameter, Signature, signature
>>> from functools import partial
>>>
>>> def mult(x: float, /, y=1, *, z: int=1): ...
>>> params_dicts = map(pyparam_to_dict, signature(mult).parameters.values())
>>> # see that we can recover the original signature from these dicts
>>> assert Signature(map(lambda kw: Parameter(**kw), params_dicts)) == signature(mult)
```

Now what about the kv_trans? It’s default is made to return None when a value is equal to
`Parameter.empty` (which is the way the inspect module distinguishes the `None` object from
“it’s just not there”.

But we could provide our own kv_trans, which should be a function taking `(k, v)` pair
(those k and v arg names are imposed!) and returns… well, what ever you want to return
really. But you if return None, the `(k, v)` item will be skipped.

Look here how using `kv_trans=pyparam_to_dict.kv_trans.with_str_kind` does the job
of skipping `Parameter.empty` items, but also cast the `kind` value to a string,
so that it can be jsonizable.

```pycon
>>> params_to_jdict = partial(pyparam_to_dict, kv_trans=pyparam_to_dict.kv_trans.with_str_kind)
>>> got = list(map(params_to_jdict, signature(mult).parameters.values()))
>>> expected = [
...     {'name': 'x', 'kind': 'POSITIONAL_ONLY', 'annotation': float},
...     {'name': 'y', 'kind': 'POSITIONAL_OR_KEYWORD', 'default': 1},
...     {'name': 'z', 'kind': 'KEYWORD_ONLY', 'default': 1, 'annotation': int}]
>>> assert got == expected, f"\n  got={got}\n  expected={expected}"
```
