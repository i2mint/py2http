# py2http.config

The code module provides functions for retrieving configuration values for a
function based on a hierarchy of sources, including function properties,
configuration dictionaries, and default values. The `get_result` function is used to
allow nested configurations by function name, with an example provided in the docstring
for illustration.

The `mk_config` function is used to get a configuration value for a function by checking
the function properties, configuration dictionaries, and default values. It also allows
for specifying the expected type of the output, with options to provide additional
options such as the function name and expected type.

Overall, the module helps manage and retrieve configuration values for functions,
ensuring they are appropriately set and validated based on the function’s requirements.

### Functions

| [`get_result`](#py2http.config.get_result)(configs, func, funcname, key, options)   | this is meant to allow nested configs by function name example:   |
|------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------|
| [`mk_config`](#py2http.config.mk_config)(key, func, configs, defaults, ...)        | Get a config value for a function.                                |

### py2http.config.get_result(configs, func, funcname, key, options)

this is meant to allow nested configs by function name
example:

# TODO: See mk_config use and make an actual doctest for get_result
# >>> def create_something():
# …    pass
# >>> example_configs = {‘http_method’: {
# …    ‘create_something’: ‘post’,
# …    ‘get_something’: ‘get’,
# … }}
# >>> defaults = {‘create_something’: ‘DEFAULTED’}
# >>> get_result(example_configs, create_something, ‘create_something’, ‘http_method’, defaults)
# ‘post’

### py2http.config.mk_config(key, func, configs, defaults, \*\*options)

Get a config value for a function. First checks the properties of the function,
then the configs, then the defaults.

* **Parameters:**
  * **key** – The key to search for
  * **func** – The function associated with the config
  * **configs** – A config dict to search
  * **defaults** – The default configs to fall back on
  * **\*\*options** – Additional options
* **Keyword Arguments:**
  * *funcname*
    The name of the function, if not the same as func._\_name_\_
  * *type*
    The expected type of the output (use Callable for functions)
