# py2http.auth

Framework-independent credential checks, shared by the aiohttp middleware
(`py2http.middleware`) and the Bottle plugins (`py2http.bottle_plugins`), so that
both refuse the same tokens and keys for the same reasons.

```pycon
>>> bearer_token('Bearer abc'), bearer_token('bearer abc'), bearer_token('Basic abc')
('abc', 'abc', '')
>>> key_matches('k-123', 'k-123'), key_matches('k-12', 'k-123'), key_matches(None, 'k')
(True, False, False)
```

### Functions

| [`bearer_token`](#py2http.auth.bearer_token)(authorization_header)               | The token of an `Authorization: Bearer <token>` header, or `''`.                                                       |
|---------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------|
| [`decode_jwt`](#py2http.auth.decode_jwt)(token, secret, \*, algorithms[, ...]) | The claims of `token`, or `CredentialsRejected` with a client-safe reason.                                             |
| [`jwt_algorithms`](#py2http.auth.jwt_algorithms)(secret, \*[, verify, ...])        | Validate a JWT verification setup, returning the algorithms as a list.                                                 |
| [`jwt_decode_kwargs`](#py2http.auth.jwt_decode_kwargs)([decode_kwargs])               | Validate extra `jwt.decode` arguments (`audience`, `issuer`, `leeway`...), refusing those the verification setup owns. |
| [`key_matches`](#py2http.auth.key_matches)(given, expected)                     | Whether the `given` credential equals `expected`, in constant time.                                                    |
| [`required_key`](#py2http.auth.required_key)(key, \*[, name])                    | `key`, refused when empty: an empty key would let a request with no `Authorization` header through.                    |

### Classes

| [`AuthPlugin`](#py2http.auth.AuthPlugin)()   | What a plugin must be to guard a Flask app (see `py2http.flask_plugins`): a subclass with a `challenge` (the `WWW-Authenticate` value of a refusal) and an `authenticate` that raises `CredentialsRejected` to refuse a request.   |
|-----------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

### Exceptions

| [`CredentialsRejected`](#py2http.auth.CredentialsRejected)   | A request's credentials were refused.   |
|------------------------------------------------------------------------|-----------------------------------------|

### *class* py2http.auth.AuthPlugin

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What a plugin must be to guard a Flask app (see `py2http.flask_plugins`): a
subclass with a `challenge` (the `WWW-Authenticate` value of a refusal) and an
`authenticate` that raises `CredentialsRejected` to refuse a request. It is a
marker class rather than a duck-typed method name, so that a plugin which merely has
some `authenticate` method (returning `False` to refuse, say) can’t be mistaken
for one and let everything through.

#### authenticate(authorization_header, , method, endpoint)

The claims to put on the request, or `None`; `CredentialsRejected` refuses.

### *exception* py2http.auth.CredentialsRejected

Bases: [`Exception`](https://docs.python.org/3/builtins/exceptions.html#Exception)

A request’s credentials were refused. The message is safe to show the client:
it never contains the token, nor anything about the server’s key.

### py2http.auth.bearer_token(authorization_header)

The token of an `Authorization: Bearer <token>` header, or `''`.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### py2http.auth.decode_jwt(token, secret, , algorithms, verify=True, decode_kwargs=None)

The claims of `token`, or `CredentialsRejected` with a client-safe reason.

With `verify=False` neither the signature nor the claims (`exp`…) are checked.
`decode_kwargs` (`audience`, `issuer`, `leeway`…) go to `jwt.decode`.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

### py2http.auth.jwt_algorithms(secret, , verify=True, algorithms=('HS256',), allow_mixed_algorithm_families=False)

Validate a JWT verification setup, returning the algorithms as a list.

Raises at construction time, rather than accepting forgeries at request time, when:

- `algorithms` is empty, a bare string, or names an unknown or unsigned (`none`)
  algorithm (PyJWT names are case-sensitive);
- `verify` is True and `secret` is empty (an empty HMAC secret lets anyone sign
  tokens), or an HMAC algorithm is asked for with a non-`str`/`bytes` secret;
- `verify` is True and HMAC and public-key algorithms are mixed with one
  `secret` (the classic algorithm-confusion setup), unless
  `allow_mixed_algorithm_families` is True.

```pycon
>>> jwt_algorithms('s3cret')
['HS256']
>>> jwt_algorithms('', algorithms=['HS256'])
Traceback (most recent call last):
  ...
ValueError: secret must be a non-empty key when verify=True
```

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

### py2http.auth.jwt_decode_kwargs(decode_kwargs=None)

Validate extra `jwt.decode` arguments (`audience`, `issuer`,
`leeway`…), refusing those the verification setup owns.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)

```pycon
>>> jwt_decode_kwargs({'audience': 'my-api'})
{'audience': 'my-api'}
>>> jwt_decode_kwargs({'options': {'verify_signature': False}})
Traceback (most recent call last):
  ...
ValueError: decode_kwargs may not set ['options']; use verify= and algorithms=
```

### py2http.auth.key_matches(given, expected)

Whether the `given` credential equals `expected`, in constant time.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### py2http.auth.required_key(key, , name='api_key')

`key`, refused when empty: an empty key would let a request with no
`Authorization` header through.
