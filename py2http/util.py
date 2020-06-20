from typing import Callable


class ModuleNotFoundIgnore:
    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is ModuleNotFoundError:
            pass
        return True


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
            assert isinstance(v, types), f'Invalid {k} type, must be a {types}, but was a {type(v)}'
        elif self.if_kind_missing == 'ignore':
            pass
        elif self.if_kind_missing == 'raise':
            raise ValueError(f"Unrecognized kind: {k}. The ones I recognize: {list(self.types_for_kind.keys())}")
        elif self.if_kind_missing == 'warn':
            from warnings import warn
            warn(f"Unrecognized kind: {k}. The ones I recognize: {list(self.types_for_kind.keys())}")


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
    >>> for t in [(A, ('foo',)), (A, ('B',)), (A, ('B', 'bar'))]:
    ...     assert obj_to_path(path_to_obj(*t)) == t
    """
    if hasattr(obj, '__qualname__') and hasattr(obj, '__globals__'):
        root_name, *attr_path = obj.__qualname__.split('.')
        return obj.__globals__[root_name], tuple(attr_path)
    else:
        return obj
