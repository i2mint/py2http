from typing import Optional, Callable, Union, Iterable, Any
from inspect import Parameter, signature
from multiprocessing.context import Process
from multiprocessing import Queue, active_children
from time import sleep, time
from functools import wraps, partial
from warnings import warn, simplefilter
from contextlib import contextmanager
from strand import run_process

from glom import Spec  # NOTE: Third-party


class lazyprop:
    """
    A descriptor implementation of lazyprop (cached property).
    Made based on David Beazley's "Python Cookbook" book and enhanced with boltons.cacheutils ideas.

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
    """

    def __init__(self, func):
        self.__doc__ = getattr(func, '__doc__')
        self.__isabstractmethod__ = getattr(func, '__isabstractmethod__', False)
        self.func = func

    def __get__(self, instance, cls):
        if instance is None:
            return self
        else:
            value = instance.__dict__[self.func.__name__] = self.func(instance)
            return value

    def __repr__(self):
        cn = self.__class__.__name__
        return '<%s func=%s>' % (cn, self.func)


def if_not_empty(obj, if_empty_val=None):
    if obj != Parameter.empty:
        return obj
    else:
        return if_empty_val


none_if_not_empty = partial(if_not_empty, if_not_empty=None)

func_info_spec = Spec(
    {
        'name': '__name__',
        'qualname': '__qualname__',
        'module': '__module__',
        'return_annotation': (signature, 'return_annotation', none_if_not_empty,),
        'params': (signature, 'parameters'),
    }
)


def py_obj_info(obj):
    return func_info_spec.glom(obj)


def conditional_logger(verbose=False, log_func=print):
    if verbose:
        return log_func
    else:

        def clog(*args, **kwargs):
            pass  # do nothing

        return clog


class CreateProcess:
    """A context manager to launch a parallel process and close it on exit.
    """

    def __init__(
        self,
        proc_func: Callable,
        process_name=None,
        wait_before_entering=2,
        verbose=False,
        args=(),
        **kwargs,
    ):
        """
        Essentially, this context manager will call
        ```
            proc_func(*args, **kwargs)
        ```
        in an independent process.

        :param proc_func: A function that will be launched in the process
        :param process_name: The name of the process.
        :param wait_before_entering: A pause (in seconds) before returning from the enter phase.
            (in case the outside should wait before assuming everything is ready)
        :param verbose: If True, will print some info on the starting/stoping of the process
        :param args: args that will be given as arguments to the proc_func call
        :param kwargs: The kwargs that will be given as arguments to the proc_func call

        The following should print 'Hello console!' in the console.
        >>> with CreateProcess(print, verbose=True, args=('Hello console!',)) as p:
        ...     print("-------> Hello module!")  # doctest: +ELLIPSIS, +NORMALIZE_WHITESPACE
        Starting process: print...
        ... print process started.
        -------> Hello module!
        ... print process terminated
        """
        self.proc_func = proc_func
        self.process_name = process_name or getattr(proc_func, '__name__', '')
        self.wait_before_entering = float(wait_before_entering)
        self.verbose = verbose
        self.args = args
        self.kwargs = kwargs
        self.clog = conditional_logger(verbose)
        self.process = None
        self.exception_info = None

    def process_is_running(self):
        return self.process is not None and self.process.is_alive()

    def __enter__(self):
        self.process = Process(
            target=self.proc_func,
            args=self.args,
            kwargs=self.kwargs,
            name=self.process_name,
        )
        self.clog(f'Starting process: {self.process_name}...')
        try:
            self.process.start()
            if self.process_is_running():
                self.clog(f'... {self.process_name} process started.')
                sleep(self.wait_before_entering)
                return self
            else:
                raise RuntimeError('Process is not running')
        except Exception:
            raise RuntimeError(
                f'Something went wrong when trying to launch process {self.process_name}'
            )

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.process is not None and self.process.is_alive():
            self.clog(f'Terminating process: {self.process_name}...')
            self.process.terminate()
        self.clog(f'... {self.process_name} process terminated')
        if exc_type is not None:
            self.exception_info = dict(
                exc_type=exc_type, exc_val=exc_val, exc_tb=exc_tb
            )


def deprecate(func=None, *, msg=None):
    """Decorator to emit a DeprecationWarning when the decorated function is called."""
    if func is None:
        return partial(deprecate, msg=msg)
    else:
        assert callable(func), f'func should be callable. Was {func}'
        msg = msg or f'{func.__qualname__} is being deprecated.'

        @wraps(func)
        def deprecated_func(*args, **kwargs):
            simplefilter('always', DeprecationWarning)  # turn off filter
            warn(msg, category=DeprecationWarning, stacklevel=2)
            simplefilter('default', DeprecationWarning)  # reset filter
            return func(*args, **kwargs)

        return deprecated_func


class Missing:
    """A class to use as a value to indicate that something was missing"""

    def __init__(self, val=None):
        self.val = val


class Skip:
    """Class to indicate if one should skip an item"""


def obj_to_items_gen(
    obj,
    attrs: Iterable[str],
    on_missing_attr: Union[Callable, Skip, None] = Missing,
    kv_trans: Optional[Callable] = lambda k, v: (k, v)
    if v is not Parameter.empty
    else None,
):
    """Make a generator of (k, v) items extracted from an input object, given an iterable of attributes to extract

    :param obj: A python object
    :param attrs: The iterable of attributes to extract from obj
    :param on_missing_val: What to do if an attribute is missing:
        - Skip: Skip the item
        - Callable: Call a function with the attribute as an input
        - anything else: Just return that as a value
    :param kv_trans:
    :return: A generator
    """

    def gen():
        for k in attrs:
            v = getattr(obj, k, Missing)
            if v is Missing:
                if on_missing_attr is obj_to_items_gen.Skip:
                    continue  # skip this
                elif callable(on_missing_attr):
                    yield k, on_missing_attr(k)
                else:
                    yield k, on_missing_attr

            yield k, getattr(obj, k, on_missing_attr)

    if kv_trans is not None:
        assert callable(kv_trans)
        assert list(signature(kv_trans).parameters) == [
            'k',
            'v',
        ], f'kv_trans must have signature (k, v)'
        _gen = gen

        def gen():
            for k, v in _gen():
                x = kv_trans(k=k, v=v)
                if x is not None:
                    yield x

    return gen


obj_to_items_gen.Skip = Skip


class _pyparam_kv_trans:
    """A collection of kv_trans functions for pyparam_to_dict"""

    @staticmethod
    def skip_empties(k, v):
        return (k, v) if v is not Parameter.empty else None

    @staticmethod
    def with_str_kind(k, v):
        if v is Parameter.empty:
            return None
        elif k == 'kind':
            return k, str(v)
        else:
            return k, v


def pyparam_to_dict(param, kv_trans: Callable = _pyparam_kv_trans.skip_empties):
    """Get dict from a Parameter object

    :param param: A inspect.Parameter instance
    :param kv_trans: A callable that will be called on the (k, v) attribute items of the Parameter instance
    :return: A dict extracted from this Parameter

    >>> from inspect import Parameter, Signature, signature
    >>> from functools import partial
    >>>
    >>> def mult(x: float, /, y=1, *, z: int=1): ...
    >>> params_dicts = map(pyparam_to_dict, signature(mult).parameters.values())
    >>> # see that we can recover the original signature from these dicts
    >>> assert Signature(map(lambda kw: Parameter(**kw), params_dicts)) == signature(mult)

    Now what about the kv_trans? It's default is made to return None when a value is equal to
    `Parameter.empty` (which is the way the inspect module distinguishes the `None` object from
    "it's just not there".

    But we could provide our own kv_trans, which should be a function taking `(k, v)` pair
    (those k and v arg names are imposed!) and returns... well, what ever you want to return
    really. But you if return None, the `(k, v)` item will be skipped.

    Look here how using `kv_trans=pyparam_to_dict.kv_trans.with_str_kind` does the job
    of skipping `Parameter.empty` items, but also cast the `kind` value to a string,
    so that it can be jsonizable.

    >>> params_to_jdict = partial(pyparam_to_dict, kv_trans=pyparam_to_dict.kv_trans.with_str_kind)
    >>> got = list(map(params_to_jdict, signature(mult).parameters.values()))
    >>> expected = [
    ...     {'name': 'x', 'kind': 'POSITIONAL_ONLY', 'annotation': float},
    ...     {'name': 'y', 'kind': 'POSITIONAL_OR_KEYWORD', 'default': 1},
    ...     {'name': 'z', 'kind': 'KEYWORD_ONLY', 'default': 1, 'annotation': int}]
    >>> assert got == expected, f"\\n  got={got}\\n  expected={expected}"

    """
    gen = obj_to_items_gen(
        param,
        attrs=('name', 'kind', 'default', 'annotation'),
        on_missing_attr=None,
        kv_trans=kv_trans,
    )

    return dict(gen())


pyparam_to_dict.kv_trans = _pyparam_kv_trans


class ModuleNotFoundIgnore:
    """Context manager to ignore ModuleNotFoundErrors.

    When all goes well, code is executed normally:
    >>> with ModuleNotFoundIgnore():
    ...     import os.path  # test when the module exists
    ...     # The following code is reached and executed
    ...     print('hi there!')
    ...     print(str(os.path.join)[:14] + '...')  # code is reached
    hi there!
    <function join...

    But if you try to import a module that doesn't exist on your system,
    the block will be skipped from that point onward, silently.
    >>> with ModuleNotFoundIgnore():
    ...     import do.i.exist
    ...     # The following code is NEVER reached or executed
    ...     print(do.i.exist)
    ...     t = 0 / 0


    But if there's any other kind of error (other than ModuleNotFoundError that is,
    the error will be raised normally.
    >>> with ModuleNotFoundIgnore():
    ...     t = 0/0
    Traceback (most recent call last):
      ...
    ZeroDivisionError: division by zero"""

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is ModuleNotFoundError:
            return True

        # else:
        #     return True


class TypeAsserter:
    """Makes a callable that asserts that a value `v` has the expected type(s) that it's kind `k` should be

    >>> assert_type = TypeAsserter({'foo': str, 'bar': (Callable, type(None))})
    >>> assert_type('bar', lambda x: x)
    >>> assert_type('bar', None)
    >>> assert_type('foo', 'i am a string')
    >>> assert_type('foo', list('i am not a string'))
    Traceback (most recent call last):
      ...
    AssertionError: Invalid foo type, must be a <class 'str'>, but was a <class 'list'>

    If a kind wasn't specified, the default is to ignore

    >>> assert_type('not_a_kind', 'blah')
    >>> assert_type = TypeAsserter({'foo': str, 'bar': (Callable, type(None))})  # nothing happens

    But you can choose to warn or raise an exception instead

    >>> assert_type = TypeAsserter({'foo': str, 'bar': list}, if_kind_missing='raise')
    >>> assert_type('not_a_kind', 'blah')
    Traceback (most recent call last):
        ...
    ValueError: Unrecognized kind: not_a_kind. The ones I recognize: ['foo', 'bar']

    """

    def __init__(self, types_for_kind, if_kind_missing='ignore'):
        self.types_for_kind = types_for_kind
        assert if_kind_missing in {'ignore', 'raise', 'warn'}
        self.if_kind_missing = if_kind_missing

    def __call__(self, k, v):
        types = self.types_for_kind.get(k, None)
        if types is not None:
            assert isinstance(
                v, types
            ), f'Invalid {k} type, must be a {types}, but was a {type(v)}'
        elif self.if_kind_missing == 'ignore':
            pass
        elif self.if_kind_missing == 'raise':
            raise ValueError(
                f'Unrecognized kind: {k}. The ones I recognize: {list(self.types_for_kind.keys())}'
            )
        elif self.if_kind_missing == 'warn':
            from warnings import warn

            warn(
                f'Unrecognized kind: {k}. The ones I recognize: {list(self.types_for_kind.keys())}'
            )


def path_to_obj(root_obj, attr_path):
    """Get an object from a root object and "attribute path" specification.

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
    """
    obj = root_obj
    for attr in attr_path:
        obj = getattr(obj, attr)
    return obj


# TODO: I'd like to find a better way to do this. Using globals() here.
#   See https://stackoverflow.com/questions/62416006/getting-the-attribute-path-of-a-python-object
def obj_to_path(obj):
    """Quasi-inverse of obj_to_path: Get a root_obj and attr_path from an object.
    Obviously, would only be able to work with some types (only by-ref types?).

    >>> class A:
    ...     def foo(self, x): ...
    ...     foo.x = 3
    ...     class B:
    ...         def bar(self, x): ...
    ...
    >>> for t in [(A, ('foo',)), (A, ('B',)), (A, ('B', 'bar'))]: # doctest: +SKIP
    ...     print(obj_to_path(path_to_obj(*t)))
    ...     print(t)
    ...     print()
    (<class 'util.A'>, ('foo',))
    (<class 'util.A'>, ('foo',))
    <BLANKLINE>
    <class 'util.A.B'>
    (<class 'util.A'>, ('B',))
    <BLANKLINE>
    (<class 'util.A'>, ('B', 'bar'))
    (<class 'util.A'>, ('B', 'bar'))
    <BLANKLINE>

    # >>> for t in [(A, ('foo',)), (A, ('B',)), (A, ('B', 'bar'))]:
    # ...     assert obj_to_path(path_to_obj(*t)) == t
    """
    if hasattr(obj, '__qualname__') and hasattr(obj, '__globals__'):
        root_name, *attr_path = obj.__qualname__.split('.')
        return obj.__globals__[root_name], tuple(attr_path)
    else:
        return obj
