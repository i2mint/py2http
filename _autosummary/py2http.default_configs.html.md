# py2http.default_configs

This module provides default configurations, input mappers, output mappers,
and error handlers for an HTTP service implemented in Python using the py2http
library. It includes functions for handling JSON requests and responses,
as well as mapping errors to appropriate HTTP responses based on different
HTTP frameworks (AIOHTTP, BOTTLE, FLASK).

The module also defines a set of default configuration values for setting up
the HTTP service, such as the application name, framework to use, port number,
error handling strategy, and CORS settings. It provides flexibility to customize
these configurations based on the specific requirements of the project.

Overall, this module serves as a foundational component for building and setting
up an HTTP service in Python using the py2http library.

### Functions

| `aiohttp_error_handler`(error)                                                                |                                                                                                                                                                                                                                                   |
|-----------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `bottle_error_handler`(error)                                                                 |                                                                                                                                                                                                                                                   |
| `bottle_output_mapper`(output, \*\*inputs)                                                    |                                                                                                                                                                                                                                                   |
| `default_error_handler`(error)                                                                |                                                                                                                                                                                                                                                   |
| `default_input_mapper`(\*\*inputs)                                                            |                                                                                                                                                                                                                                                   |
| [`error_status`](#py2http.default_configs.error_status)(error)                          | The HTTP status for an error a handler raised (500 when it is not a client's).                                                                                                                                                                    |
| [`flask_error_handler`](#py2http.default_configs.flask_error_handler)(error)                   | The `(body, status, headers)` a Flask view returns for an error, mapped like the bottle handler (`OPAQUE_ERRORS` hides the text of a 500).                                                                                                        |
| [`flask_json_output_mapper`](#py2http.default_configs.flask_json_output_mapper)(output, \*\*inputs) | The default output mapper of a Flask app: the output as a JSON response.                                                                                                                                                                          |
| `flask_output_mapper`(output, \*\*inputs)                                                     |                                                                                                                                                                                                                                                   |
| [`flask_response_mapper`](#py2http.default_configs.flask_response_mapper)(output_mapper)         | Make a Flask view's response of what an output mapper returns.                                                                                                                                                                                    |
| [`framework_defaults`](#py2http.default_configs.framework_defaults)(framework, \*, ...)       | The error handler and output mapper to use under `framework`: the given ones, except that the defaults (which only know of Bottle and AIOHTTP) are swapped for the framework's own, so that no process-wide state decides how a response is made. |
| [`www_authenticate_challenge`](#py2http.default_configs.www_authenticate_challenge)()                 | The `WWW-Authenticate` value of a 401 a dispatched function raised: the `PY2HTTP_WWW_AUTHENTICATE` environment variable, else `Bearer` (also when the variable holds a line break, which would make every 401 fail to send).                      |

### py2http.default_configs.error_status(error)

The HTTP status for an error a handler raised (500 when it is not a client’s).

```pycon
>>> error_status(AuthorizationError()), error_status(ForbiddenError())
(401, 403)
>>> error_status(InputError()), error_status(KeyError())
(400, 500)
```

* **Return type:**
  [`int`](https://docs.python.org/3/builtins/functions.html#int)

### py2http.default_configs.flask_error_handler(error)

The `(body, status, headers)` a Flask view returns for an error, mapped like
the bottle handler (`OPAQUE_ERRORS` hides the text of a 500).

### py2http.default_configs.flask_json_output_mapper(output, \*\*inputs)

The default output mapper of a Flask app: the output as a JSON response.

### py2http.default_configs.flask_response_mapper(output_mapper)

Make a Flask view’s response of what an output mapper returns.

The `send_*_resp` decorators set Bottle’s `response.content_type` and return
the body (`str` or `bytes`); Flask ignores that and would answer `text/html`.
A mapper that declares a `content_type` and returns a `str`/`bytes` body, or a
`(body, status[, headers])` tuple of one, gets that content type (unless the tuple’s
headers set their own); an `async` mapper is awaited first. Anything else (a
`Response`, a dict) is kept as is.

```pycon
>>> from py2http.decorators import send_raw_resp  # (needs flask)
>>> flask_response_mapper(send_raw_resp(lambda o: o))(b"x").content_type
'text/plain'
```

### py2http.default_configs.framework_defaults(framework, , error_handler, output_mapper)

The error handler and output mapper to use under `framework`: the given ones,
except that the defaults (which only know of Bottle and AIOHTTP) are swapped for
the framework’s own, so that no process-wide state decides how a response is made.

```pycon
>>> framework_defaults(FLASK, error_handler=default_error_handler,
...     output_mapper=default_output_mapper)[0] is flask_error_handler
True
```

### py2http.default_configs.www_authenticate_challenge()

The `WWW-Authenticate` value of a 401 a dispatched function raised: the
`PY2HTTP_WWW_AUTHENTICATE` environment variable, else `Bearer` (also when the
variable holds a line break, which would make every 401 fail to send).

```pycon
>>> os.environ.pop(WWW_AUTHENTICATE_ENV_VAR, None) and None
>>> www_authenticate_challenge()
'Bearer'
```

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
