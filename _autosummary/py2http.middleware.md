# py2http.middleware

py2http is a Python module that allows you to dispatch Python functions as HTTP
services.
By running a basic HTTP service from a list of functions, you can access OpenAPI
specifications, Swagger documentation, and utilize the HTTP service’s routes.
Additionally, Py2http provides features for method transformation, input mapping,
output mapping, error handling, and client generation.

The code snippet provided below is a part of Py2http module and includes middleware
functions for handling JWT authentication and superadmin authorization.
These middleware functions are designed to be used within the Py2http framework to
ensure secure and authenticated access to HTTP routes.

Include the following docstring to describe this module:
“Middleware functions for handling JWT authentication and superadmin authorization
within the Py2http framework. These functions ensure secure access to HTTP routes
by verifying credentials and permissions. Use these middleware functions to enforce
authentication and control access to web resources.

### Functions

| [`mk_jwt_middleware`](#py2http.middleware.mk_jwt_middleware)(secret[, verify, ...])   | Make an aiohttp middleware that requires a valid `Authorization: Bearer` JWT on every request, and puts the decoded claims on `request.token`.   |
|---------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------|
| `mk_superadmin_middleware`(secret)                                                          |                                                                                                                                                  |

### py2http.middleware.mk_jwt_middleware(secret, verify=True, , algorithms=('HS256',), public_routes=('ping', 'openapi'), allow_mixed_algorithm_families=False)

Make an aiohttp middleware that requires a valid `Authorization: Bearer`
JWT on every request, and puts the decoded claims on `request.token`.

* **Parameters:**
  * **secret** – The key tokens are verified with (an HMAC secret for `HS*`
    algorithms, a public key for `RS*`/`ES*`/…).
  * **verify** – If False, signatures and claims (`exp`, …) are NOT checked:
    whatever a token says ends up on `request.token`, and an
    undecodable token only triggers a warning. For development only.
    (Before, PyJWT 2 ignored the legacy option this passed, so
    signatures were still checked even with `verify=False`.)
  * **algorithms** ([`Iterable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterable)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – The algorithms a token may be signed with (PyJWT names,
    case-sensitive; `"none"` is refused). Defaults to `("HS256",)`,
    as `py2http.bottle_plugins.JWTPlugin` does.
  * **public_routes** ([`Iterable`](https://docs.python.org/3/library/collections.abc.html#collections.abc.Iterable)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]) – Names of aiohttp routes (`name=` in `add_route`) that
    need no token. Matched on the route name, not the handler’s
    `__name__`, so a handler that happens to be called `ping` is not
    public by accident. Route names are matched in sub-applications
    too, so a sub-app route named `ping` is public as well.
  * **allow_mixed_algorithm_families** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – Accepting an HMAC algorithm and a
    public-key algorithm with one `secret` is the classic
    algorithm-confusion setup (a token “signed” with HS256 using the
    public key as the HMAC secret), so it raises `ValueError` unless
    this is True. The middleware used to accept `["HS256", "RS256"]`;
    pass that list with this flag to restore it.
