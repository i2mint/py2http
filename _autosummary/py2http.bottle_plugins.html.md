# py2http.bottle_plugins

Plugins for adding middleware functionality to Bottle apps.

### Classes

| [`ApiKeyAuthPlugin`](#py2http.bottle_plugins.ApiKeyAuthPlugin)(api_key)                | A plugin letting through only requests whose `Authorization` header is exactly `api_key` (compared in constant time; an empty key is refused).   |
|-------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------|
| `CorsPlugin`([origins])                                                                   |                                                                                                                                                  |
| [`JWTPlugin`](#py2http.bottle_plugins.JWTPlugin)([secret, verify, mapper, ...]) | A plugin for validating JWTs and extracting their payloads.                                                                                      |

### *class* py2http.bottle_plugins.ApiKeyAuthPlugin(api_key)

Bases: [`AuthPlugin`](py2http.auth.html.md#py2http.auth.AuthPlugin)

A plugin letting through only requests whose `Authorization` header is
exactly `api_key` (compared in constant time; an empty key is refused).

#### authenticate(authorization_header, , method, endpoint)

`None` (the key sets nothing on the request) if the header is the key,
else `CredentialsRejected`. Framework-independent, like `JWTPlugin`’s.

### *class* py2http.bottle_plugins.JWTPlugin(secret='', verify=True, mapper=None, ignore_methods=None, algorithms=None, , allow_mixed_algorithm_families=False, decode_kwargs=None)

Bases: [`AuthPlugin`](py2http.auth.html.md#py2http.auth.AuthPlugin)

A plugin for validating JWTs and extracting their payloads.

After optionally validating a JWT found in the request header, will assign a dict with the JWT claims
to request.token.

#### authenticate(authorization_header, , method, endpoint)

The claims to put on the request (`None` when there are none to put), or
`CredentialsRejected`. Framework-independent: the Bottle plugin and the Flask
`before_request` hook (`py2http.flask_plugins`) both call it.
