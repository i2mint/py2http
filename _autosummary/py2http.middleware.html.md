# py2http.middleware

aiohttp middleware that guards every route of an app: `mk_jwt_middleware`
(a verified `Authorization: Bearer` JWT) and `mk_superadmin_middleware` (one
shared key). The checks themselves live in `py2http.auth`, shared with the Bottle
plugins of `py2http.bottle_plugins`.

### Functions

| [`mk_jwt_middleware`](#py2http.middleware.mk_jwt_middleware)(secret[, verify, ...])   | Make an aiohttp middleware that requires a valid `Authorization: Bearer` JWT on every request, and puts the decoded claims on `request.token`.   |
|---------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------|
| [`mk_superadmin_middleware`](#py2http.middleware.mk_superadmin_middleware)(secret)           | Make an aiohttp middleware that only lets through requests whose `Authorization` header is exactly `secret` (compared in constant time).         |

### py2http.middleware.mk_jwt_middleware(secret, verify=True, , algorithms=('HS256',), public_routes=('ping', 'openapi'), allow_mixed_algorithm_families=False, decode_kwargs=None)

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
  * **decode_kwargs** ([`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)) – Extra `jwt.decode` arguments, such as `audience`,
    `issuer` or `leeway` (without them a token carrying an `aud`
    claim is always refused).

### py2http.middleware.mk_superadmin_middleware(secret)

Make an aiohttp middleware that only lets through requests whose
`Authorization` header is exactly `secret` (compared in constant time).
An empty `secret` is refused, since it would let header-less requests through.
