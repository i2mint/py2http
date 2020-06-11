from functools import wraps


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
