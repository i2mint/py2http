# py2http.openapi_utils

This module is designed to generate OpenAPI specifications based on Python functions.
It includes functions for creating OpenAPI paths, setting authentication details,
and building OpenAPI templates. The `OpenApiExtractor` class can be used to extract
information from an existing OpenAPI document.

The `func_to_openapi_spec` function is particularly useful, as it takes a Python
function as input and generates an OpenAPI path specification, including request
and response schemas.

Overall, this module allows you to define API routes and generate corresponding
OpenAPI specifications directly from your Python functions. It provides a convenient
way to document and expose your functions as HTTP endpoints.

### Functions

| `add_paths_to_spec`(paths_spec, new_paths)                                                |    |
|-------------------------------------------------------------------------------------------|----|
| `func_to_openapi_spec`(func[, exclude_keys, ...])                                         |    |
| `mk_arg_schema`(arg)                                                                      |    |
| `mk_obj_schema`(request_object)                                                           |    |
| `mk_openapi_path`([pathname, method, ...])                                                |    |
| `mk_openapi_template`([config])                                                           |    |
| `openapi_type_mapping`(obj_type)                                                          |    |
| [`set_auth`](#py2http.openapi_utils.set_auth)(openapi_spec[, auth_type, ...]) |    |

### Classes

| `OpenApiExtractor`(openapi_spec[, func_to_path])   |    |
|----------------------------------------------------|----|

### py2http.openapi_utils.set_auth(openapi_spec, auth_type='jwt', , login_details=None)

* **Parameters:**
  * **openapi_spec** – An OpenAPI formatted server specification
  * **auth_type** – Either ‘jwt’ or ‘api_key’
  * **login_details** – Optional - {
    ‘login_url’: the login url
    ‘refresh_url’: the refresh url, if applicable
    ‘login_inputs’: a list of strings e.g. [‘account’, ‘email’, ‘password’]
    ‘refresh_inputs’: a list of strings e.g. [‘account’, ‘refresh_token’]
    ‘outputs’: a list of strings e.g. [‘jwt’, ‘refresh_token’]
    }
    “”
