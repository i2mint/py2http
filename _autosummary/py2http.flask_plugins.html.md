# py2http.flask_plugins

Flask counterparts of the Bottle plugins: auth as a `before_request` hook, CORS as an
`after_request` hook.

The credential checks are the plugins’ own (`JWTPlugin.authenticate`,
`ApiKeyAuthPlugin.authenticate`, which call `py2http.auth`), so Bottle and Flask
refuse the same requests for the same reasons. A plugin without an `authenticate`
method is a Bottle-only plugin: it is refused with `NotImplementedError` rather than
dropped, because a silently dropped auth plugin would leave its routes open.

### Functions

| [`check_flask_plugins`](#py2http.flask_plugins.check_flask_plugins)(plugins)                    | The `plugins` as a list, each known to work under Flask; else `NotImplementedError`.   |
|--------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------|
| [`mk_auth_hook`](#py2http.flask_plugins.mk_auth_hook)(plugins, \*, public_views[, cors]) | A `before_request` function running `plugins` (outermost first, as under Bottle).      |
| [`mk_cors_hook`](#py2http.flask_plugins.mk_cors_hook)([origins])                         | An `after_request` function adding the CORS headers `CorsPlugin` adds.                 |

### py2http.flask_plugins.check_flask_plugins(plugins)

The `plugins` as a list, each known to work under Flask; else `NotImplementedError`.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)

```pycon
>>> check_flask_plugins(None)
[]
>>> check_flask_plugins([object()])
Traceback (most recent call last):
  ...
NotImplementedError: The plugin <object object at ...> is Bottle-only...
```

### py2http.flask_plugins.mk_auth_hook(plugins, , public_views, cors=False)

A `before_request` function running `plugins` (outermost first, as under Bottle).

Everything is guarded except: the `public_views` (the view *functions* themselves,
not endpoint names: a user function named `openapi` must stay guarded); a request that matched no
route (it answers 404/405, as under Bottle, and runs no view); and, with `cors`,
the `OPTIONS` preflight, which Bottle’s CORS plugin answers before any auth runs.
A plugin’s claims go on `request.token`, where the endpoint finds them through
`current_request`.

### py2http.flask_plugins.mk_cors_hook(origins='\*')

An `after_request` function adding the CORS headers `CorsPlugin` adds.

Flask answers the `OPTIONS` preflight itself, so this only adds the headers.
