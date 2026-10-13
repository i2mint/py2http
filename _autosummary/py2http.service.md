# py2http.service

This Python module provides a framework for dispatching Python functions as HTTP
services and generating OpenAPI specifications for these services.
It includes functionality for handling input mappers, output mappers, error handling,
configuration, and client generation.

The module defines functions for creating and running web applications that expose
Python functions as API endpoints. It supports various web frameworks like Flask,
Bottle, and aiohttp for running these applications.

Additionally, the module allows for creating multi-service applications by defining
routes per API with a list of handlers for each API. It also supports publishing
OpenAPI specifications and Swagger documentation for the APIs.

Overall, this module offers a comprehensive approach to creating HTTP services from
Python functions, enabling developers to easily expose their functions as remote APIs
with minimal setup.

### Functions

| `func_copy`(func)                                                                                 |                                                                                                                   |
|---------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------------------|
| `method_not_found`(method_name)                                                                   |                                                                                                                   |
| `mk_aiohttp_app`(funcs, \*\*configs)                                                              |                                                                                                                   |
| [`mk_app`](#py2http.service.mk_app)(app_spec, \*[, app_name, framework, ...]) | Generates an application which exposes web services created from the given python functions to remotely run them. |
| `mk_bottle_app`(funcs, \*\*configs)                                                               |                                                                                                                   |
| `mk_flask_app`(funcs, \*\*configs)                                                                |                                                                                                                   |
| [`mk_route`](#py2http.service.mk_route)(func, \*\*configs)                      | Generate a route object and an OpenAPI path specification for a function                                          |
| `mk_routes_and_openapi_specs`(funcs, \*\*configs)                                                 |                                                                                                                   |
| [`public_attr`](#py2http.service.public_attr)(obj, attr_name)                      | The attribute policy `attr_names='*'` stands for: only public methods.                                            |
| [`run_app`](#py2http.service.run_app)(app_obj, \*[, app_name, framework, ...]) | Run an application which exposes web services created from the given python functions to remotely run them.       |
| [`unsafe_any_attr`](#py2http.service.unsafe_any_attr)(obj, attr_name)                  | Dispatch ANY attribute of the object, including private ones and dunders.                                         |

### Classes

| [`LRUObjStore`](#py2http.service.LRUObjStore)(\*[, max_size])   | A mapping that keeps at most `max_size` items, evicting the least recently used one when a new key would exceed it.   |
|--------------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------|
| [`SubAppSpec`](#py2http.service.SubAppSpec)                    |                                                                                                                       |

### *class* py2http.service.LRUObjStore(, max_size=1000)

Bases: [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)

A mapping that keeps at most `max_size` items, evicting the least recently
used one when a new key would exceed it.

Used as the default store of objects created through a class endpoint, so that
clients cannot grow server memory without bound by creating objects.

```pycon
>>> s = LRUObjStore(max_size=2)
>>> s['a'], s['b'] = 1, 2
>>> _ = s['a']  # 'a' is now the most recently used
>>> s['c'] = 3
>>> sorted(s)
['a', 'c']
```

### *class* py2http.service.SubAppSpec

Bases: [`TypedDict`](https://docs.python.org/3/library/typing.html#typing.TypedDict)

### py2http.service.mk_app(app_spec, \*, app_name='HTTP Service', framework='bottle', input_mapper=<function default_input_mapper>, output_mapper=<function send_json_resp.<locals>.output_mapper>, error_handler=<function default_error_handler>, header_inputs={}, middleware=[], host='localhost', port=3030, server='gunicorn', http_method='post', openapi={}, logger=None, plugins=[], enable_cors=False, cors_allowed_origins='\*', publish_openapi=False, openapi_insecure=False, publish_swagger=False, swagger_url='/swagger', swagger_title='Swagger', ssl_certfile=None, ssl_keyfile=None, \*\*configs)

Generates an application which exposes web services created from the given python
functions to remotely run them.
You can generate a multi-service application defining a route per API or sub
application.

First define a bunch of functions (or handlers) you want to expose as a web service.

```pycon
>>> def foo():
...     return 0
...
>>> def bar():
...     return True
...
```

Let’s make a single-service application. A single API will be generated with an
endpoint per handler, plus an auto-generated enpoints to ping the API.

```pycon
>>> handlers = [foo, bar]
>>> app = mk_app(handlers)
>>> app.get_url('bar')
'/bar'
>>> app.get_url('foo')
'/foo'
>>> app.get_url('ping')
'/ping'
```

You can also automatically generate an endpoint to expose the openapi specification
of your API by activating the flag “publish_openapi”. Publishing the openapi
specification will allow a client application to use the specification object to
build an interface to actually consume the API by wrapping the http layer.

```pycon
>>> app = mk_app(handlers, publish_openapi=True)
>>> app.openapi_spec
{'openapi': '3.0.2', 'info': {'title': 'default', 'version': '0.1'}, 'servers':
[{'url': 'http://localhost:3030'}], 'paths': {'/foo': {'post': {'x-method_name':
'foo', 'description': '', 'requestBody': {'required': True, 'content':
{'application/json': {'schema': {'type': 'object', 'properties': {}}}}},
'responses': {'200': {'description': '', 'content': {'application/json':
{'schema': {}}}}}}}, '/bar': {'post': {'x-method_name': 'bar', 'description': '',
'requestBody': {'required': True, 'content': {'application/json': {'schema':
{'type': 'object', 'properties': {}}}}}, 'responses': {'200': {'description': '',
'content': {'application/json': {'schema': {}}}}}}}}}
>>> app.get_url('openapi')
'/openapi'
```

You can also generate swagger documentation by activating the “publish_swagger”
flag. This will generate a swagger documentation for the API and make it available
at the specified url (by default “/swagger”).

```pycon
>>> app = mk_app(handlers, publish_openapi=True, publish_swagger=True)
```

Let’s use http2py to consume the openapi specification

```pycon
>>> from http2py import HttpClient
>>> api = HttpClient(openapi_spec=app.openapi_spec)
>>> assert(hasattr(api, 'foo'))
>>> assert(hasattr(api, 'bar'))
```

Now, let’s make a multi-service application. You only have to define a route per
API with a list of handlers for each API.

```pycon
>>> handler_spec = {
...     'foo_api': [foo],
...     'bar_api': [bar],
... }
>>> app = mk_app(handler_spec, publish_openapi=True)
>>> app.get_url('/foo_api')
'/foo_api'
>>> app.get_url('/bar_api')
'/bar_api'
```

* **Parameters:**
  * **handler_spec** (*HandlerSpec*) – The handler specification. Can be a list of python to expose,
    or a dict with a list of functions to expose per route in case of a multi-service
    application.
  * **\*\*configs** ([*dict*](https://docs.python.org/3/builtins/stdtypes.html#dict)) – The configuration for the application. See config.yaml for
    configuration documentation.

### py2http.service.mk_route(func, \*\*configs)

Generate a route object and an OpenAPI path specification for a function

* **Parameters:**
  **func** – The function
* **Keyword Arguments:**
  The configuration settings

### py2http.service.public_attr(obj, attr_name)

The attribute policy `attr_names='*'` stands for: only public methods.

A name is dispatchable if it does not start with `_` and

- for a module: it is a function that the module defines (or lists in its
  `__all__`), never something it merely imports, nor plain data;
- otherwise: it is a plain Python function, `staticmethod`,
  `classmethod` or `property` defined in the object’s class (or a base
  class), and the instance does not shadow it.

This keeps private helpers, dunders (`__dict__`, `__init__`, …),
per-instance state (`__dict__` entries, `__slots__`, dataclass and
namedtuple fields) and callables merely assigned as class attributes
(`opener = open`) out of reach of HTTP clients.

Note that every public method is exposed, inherited ones included (e.g. a
pydantic model’s `model_dump`). For anything holding secrets, or a mapping
whose mutators should stay private (`MutableMapping` mixins such as
`clear` and `pop` are plain functions), list the names explicitly instead.

```pycon
>>> class A:
...     data = 0
...     opener = open
...     def f(self): ...
...     def _g(self): ...
...     def __init__(self): self.secret = 1
>>> [public_attr(A(), name)
...  for name in ('f', '_g', '__init__', '__dict__', 'secret', 'data', 'opener')]
[True, False, False, False, False, False, False]
```

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### py2http.service.run_app(app_obj, \*, app_name='HTTP Service', framework='bottle', input_mapper=<function default_input_mapper>, output_mapper=<function send_json_resp.<locals>.output_mapper>, error_handler=<function default_error_handler>, header_inputs={}, middleware=[], host='localhost', port=3030, server='gunicorn', http_method='post', openapi={}, logger=None, plugins=[], enable_cors=False, cors_allowed_origins='\*', publish_openapi=False, openapi_insecure=False, publish_swagger=False, swagger_url='/swagger', swagger_title='Swagger', ssl_certfile=None, ssl_keyfile=None, \*\*configs)

Run an application which exposes web services created from the given python
functions to remotely run them.
You can generate a multi-service application defining a route per api or sub
application.
You can also generate the application first, then run it using this function.

* **Parameters:**
  * **app_obj** (`Union`[[`Iterable`](https://docs.python.org/3/library/typing.html#typing.Iterable)[`Union`[[`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable), `HandlerWithMappers`]], [`Dict`](https://docs.python.org/3/library/typing.html#typing.Dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), `Union`[[`Iterable`](https://docs.python.org/3/library/typing.html#typing.Iterable)[`Union`[[`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable), `HandlerWithMappers`]], [`SubAppSpec`](#py2http.service.SubAppSpec)]], [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]) – The handler specification or application object. Can be a list of
    python to expose, or a dict with a list of functions to expose per route in case
    of a multi-service. Can also be a pre-generated application object to run.
  * **\*\*configs** ([*dict*](https://docs.python.org/3/builtins/stdtypes.html#dict)) – The configuration for the application. See
    `py2http.default_configs:default_configs` for defaults and config.yaml for
    configuration documentation.

### py2http.service.unsafe_any_attr(obj, attr_name)

Dispatch ANY attribute of the object, including private ones and dunders.

This was the behaviour of `attr_names='*'` before `public_attr`: it lets a
client read `__dict__`, call `__init__` with arguments of its choosing, and so
on. Use `attr_names=unsafe_any_attr` only when every client is trusted.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)
