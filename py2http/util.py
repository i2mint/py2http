from typing import Callable


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


# default TypeAsserter used in this project
assert_type = TypeAsserter(types_for_kind={
    'input_mapper': Callable,
    'input_validator': Callable,
    'output_mapper': Callable,
})
