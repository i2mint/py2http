from typing import Callable
AIOHTTP = 'aiohttp'
FLASK = 'flask'


def get_result(configs, func, funcname, key, options):
    """ this is meant to allow nested configs by function name
    example:

    >>> def create_something():
    ...    pass
    >>> example_configs = {'http_method': {
    ...    'create_something': 'post',
    ...    'get_something': 'get',
    ... }}
    >>> mk_config(create_something, example_configs, defaults)
    'post'

    TODO: allow an $else case, other keywords, more complex parsing, and/or custom get_result functions
    """
    result = getattr(func, key, configs.get(key, None))
    if isinstance(result, dict):
        dict_value = result.get(funcname, None)
        if dict_value:
            result = dict_value
        elif '$else' in result:
            result = result['$else']
        elif options.get('type', None) is not dict:
            result = None
    return result


# TODO: Revise logic and use more appropriate tools (ChainMap, glom) and interface.
def mk_config(key, func, configs, defaults, **options):
    """
    Get a config value for a function. First checks the properties of the function,
    then the configs, then the defaults.

    :param key: The key to search for
    :param func: The function associated with the config
    :param configs: A config dict to search
    :param defaults: The default configs to fall back on
    :param **options: Additional options

    :Keyword Arguments:
        * *funcname*
          The name of the function, if not the same as func.__name__
        * *type*
          The expected type of the output (use Callable for functions)
    """
    funcname = options.get('funcname', getattr(func, '__name__', None))

    result = get_result(configs, func, funcname, key, options)

    if result:
        expected_type = options.get('type', None)  # align names expected_type <-> type
        if not expected_type:
            default_value = defaults.get(key, None)
            assert default_value is not None, f'Missing default value for key {key}'
            if callable(default_value):
                expected_type = Callable
            else:
                expected_type = type(default_value)
        assert isinstance(result, expected_type), f'Config {key} does not match type {expected_type}.'
    else:
        result = defaults.get(key, None)
    return result