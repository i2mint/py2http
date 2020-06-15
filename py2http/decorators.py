from inspect import signature, Signature


def mk_flat(cls, method, *, func_name=None):
    """
    Flatten a simple cls->instance->method call pipeline into one function.

    That is, instead of this:
    ```graphviz
    cls, init_kwargs -> instance
    instance, method, method_kwargs -> result
    ```
    you get a function `flat_func` that you can use like this:
    ```graphviz
    flat_func, init_kwargs, method_kwargs -> result
    ```
    :param cls:
    :param method:
    :param func_name:
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
        print(f'method: {method}')
        return getattr(instance, method.__name__)(**for2)

    flat_func.__signature__ = Signature(parameters, return_annotation=sig2.return_annotation)

    if func_name is not None:
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
