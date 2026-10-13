# py2http.bottle_plugins

Plugins for adding middleware functionality to Bottle apps.

### Classes

| [`ApiKeyAuthPlugin`](#py2http.bottle_plugins.ApiKeyAuthPlugin)(api_key)                | A plugin letting through only requests whose `Authorization` header is exactly `api_key` (compared in constant time; an empty key is refused).   |
|-------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------|
| `CorsPlugin`([origins])                                                                   |                                                                                                                                                  |
| [`JWTPlugin`](#py2http.bottle_plugins.JWTPlugin)([secret, verify, mapper, ...]) | A plugin for validating JWTs and extracting their payloads.                                                                                      |

### *class* py2http.bottle_plugins.ApiKeyAuthPlugin(api_key)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A plugin letting through only requests whose `Authorization` header is
exactly `api_key` (compared in constant time; an empty key is refused).

### *class* py2http.bottle_plugins.JWTPlugin(secret='', verify=True, mapper=None, ignore_methods=None, algorithms=None, , allow_mixed_algorithm_families=False, decode_kwargs=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A plugin for validating JWTs and extracting their payloads.

After optionally validating a JWT found in the request header, will assign a dict with the JWT claims
to request.token.
