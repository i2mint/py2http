# py2http.bottle_plugins

Plugins for adding middleware functionality to Bottle apps.

### Classes

| `ApiKeyAuthPlugin`(api_key)                                                               |                                                             |
|-------------------------------------------------------------------------------------------|-------------------------------------------------------------|
| `CorsPlugin`([origins])                                                                   |                                                             |
| [`JWTPlugin`](#py2http.bottle_plugins.JWTPlugin)([secret, verify, mapper, ...]) | A plugin for validating JWTs and extracting their payloads. |

### *class* py2http.bottle_plugins.JWTPlugin(secret='', verify=True, mapper=None, ignore_methods=None, algorithms=None)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A plugin for validating JWTs and extracting their payloads.

After optionally validating a JWT found in the request header, will assign a dict with the JWT claims
to request.token.
