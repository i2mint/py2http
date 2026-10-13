"""This Python module provides a framework for dispatching Python functions as HTTP
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
with minimal setup."""

import inspect
from collections import OrderedDict, deque
from contextvars import ContextVar
from collections.abc import MutableMapping
from types import ModuleType
from uuid import uuid4
from aiohttp import web
import asyncio
from copy import deepcopy
from functools import partial, wraps
from inspect import isawaitable
import json
from typing import Any, Callable, Dict, Iterable, Optional, TypedDict, Union
from types import BuiltinMethodType, FunctionType, MethodType, MethodWrapperType
import logging
import os
import sys
import threading
from bottle import Bottle, run as run_bottle
import traceback
from swagger_ui import api_doc
from i2 import name_of_obj
from i2.errors import InputError, DataError, AuthorizationError
from i2 import Sig

from py2http.bottle_plugins import CorsPlugin, OPTIONS
from py2http.config import mk_config, FLASK, AIOHTTP, BOTTLE
from py2http.default_configs import (
    default_configs,
    DFLT_CONTENT_TYPE,
    default_input_mapper,
)
from py2http.openapi_utils import (
    add_paths_to_spec,
    mk_openapi_path,
    mk_openapi_template,
)
from py2http.schema_tools import (
    mk_input_schema_from_func,
    mk_output_schema_from_func,
)
from py2http.util import TypeAsserter, call_with_inputs
from py2http.constants import JSON_CONTENT_TYPE

# Instance endpoints (``handler['endpoint']`` is an object) are one object every client
# shares; they too need an ``obj_owner`` and are bounded by ``max_obj_size`` (see
# ``_instance_endpoint_dispatcher``).
#
# Class endpoints (``handler['endpoint']`` is a class) keep the objects clients create.
# Who may use an object is the handler's ``obj_owner`` (see ``ObjOwner``); how many
# objects an owner may keep is ``obj_quota``; how many bytes each object, each owner and
# the whole endpoint may hold are ``max_obj_size``, ``max_owner_bytes`` and
# ``max_total_bytes`` (see ``_class_endpoint_dispatcher``).
#
# Maximum number of objects a class endpoint keeps alive in ``shared_objects`` mode; the
# least recently used one is evicted beyond that. Pass ``obj_store=...`` to change it.
DFLT_OBJ_STORE_MAX_SIZE = 1000
DFLT_OBJ_QUOTA = 100  # objects per owner
DFLT_MAX_OWNERS = 1000  # owners holding objects at once (least recently active evicted)
DFLT_MAX_OBJ_SIZE = 1_000_000  # bytes per object, as measured by ``obj_sizeof``
DFLT_MAX_OWNER_BYTES = 20_000_000  # bytes per owner (all their objects)
DFLT_MAX_TOTAL_BYTES = 256_000_000  # bytes per endpoint (every object of every owner)

#: The request being handled (set around every handler call), so per-request hooks such
#: as ``obj_owner`` can read it without the dispatched function taking it.
current_request: ContextVar = ContextVar("py2http_current_request", default=None)


class LRUObjStore(MutableMapping):
    """A mapping that keeps at most ``max_size`` items, evicting the least recently
    used one when a new key would exceed it (``on_evict(k, v)`` is told).

    Used as the default store of objects created through a class endpoint, so that
    clients cannot grow server memory without bound by creating objects.

    >>> s = LRUObjStore(max_size=2)
    >>> s['a'], s['b'] = 1, 2
    >>> _ = s['a']  # 'a' is now the most recently used
    >>> s['c'] = 3
    >>> sorted(s)
    ['a', 'c']
    """

    def __init__(
        self,
        *,
        max_size: int = DFLT_OBJ_STORE_MAX_SIZE,
        on_evict: Optional[Callable[[Any, Any], None]] = None,
    ):
        if max_size < 1:
            raise ValueError(f"max_size must be at least 1, got {max_size}")
        self.max_size = max_size
        self.on_evict = on_evict
        self._data = OrderedDict()

    def __getitem__(self, k):
        v = self._data[k]
        self._data.move_to_end(k)
        return v

    def __setitem__(self, k, v):
        self._data[k] = v
        self._data.move_to_end(k)
        while len(self._data) > self.max_size:
            evicted_k, evicted_v = self._data.popitem(last=False)
            if self.on_evict is not None:
                self.on_evict(evicted_k, evicted_v)

    def __delitem__(self, k):
        del self._data[k]

    def __iter__(self):
        return iter(self._data)

    def __len__(self):
        return len(self._data)


class _SharedObjects:
    """``obj_owner=shared_objects``: objects belong to no one. Any client holding an
    object id may use it, and every client's objects share one LRU store, so a client
    creating objects evicts everyone else's. Only for trusted clients."""

    def __repr__(self):
        return "shared_objects"


shared_objects = _SharedObjects()

#: ``obj_owner`` hook: ``(request) -> owner``, a hashable that identifies an
#: *authenticated* client (e.g. a user id from a verified token). ``None`` and ``""``
#: mean "not identified" and are refused. A client-chosen value (a session cookie the
#: client mints, an IP) lets one client create owners until others are evicted.
ObjOwner = Callable[[Any], Optional[Any]]


class OwnedObjStore:
    """Objects kept per owner, with object and byte budgets. Thread-safe.

    - ``quota`` objects per owner: an owner's own least recently used object is evicted
      beyond it, never someone else's;
    - ``max_owners`` owners at once: the least recently active owner's objects go;
    - byte accounting: :meth:`record` the size of an object; :meth:`owner_bytes` and
      :attr:`total_bytes` sum what is currently stored.

    >>> s = OwnedObjStore(quota=2, max_owners=2)
    >>> s.put('ann', 'a1', 1); s.put('ann', 'a2', 2); s.put('bob', 'b1', 3)
    >>> s.put('ann', 'a3', 4)  # ann's quota: her least recently used object goes
    >>> s.get('ann', 'a1') is None, s.get('ann', 'a3'), s.get('bob', 'b1')
    (True, 4, 3)
    >>> s.get('bob', 'a3') is None  # another owner's id is simply not found
    True
    >>> s.record('ann', 'a3', 100); s.record('bob', 'b1', 5)
    >>> s.owner_bytes('ann'), s.total_bytes
    (100, 105)
    """

    def __init__(
        self, *, quota: int = DFLT_OBJ_QUOTA, max_owners: int = DFLT_MAX_OWNERS
    ):
        if max_owners < 1:
            raise ValueError(f"max_owners must be at least 1, got {max_owners}")
        LRUObjStore(max_size=quota)  # validates quota now, not on first use
        self._quota = quota
        self._lock = threading.RLock()
        self._sizes: dict = {}  # (owner, obj_id) -> bytes last recorded
        self.total_bytes = 0
        self._owners = LRUObjStore(max_size=max_owners, on_evict=self._forget_owner)

    def _forget(self, owner, obj_id):
        self.total_bytes -= self._sizes.pop((owner, obj_id), 0)

    def _forget_owner(self, owner, objects):
        for obj_id in list(objects):
            self._forget(owner, obj_id)

    def _objects_of(self, owner, *, create: bool):
        objects = self._owners.get(owner)
        if objects is None and create:
            objects = LRUObjStore(
                max_size=self._quota,
                on_evict=lambda obj_id, _obj: self._forget(owner, obj_id),
            )
            self._owners[owner] = objects
        return objects

    def put(self, owner, obj_id: str, obj) -> None:
        with self._lock:
            self._objects_of(owner, create=True)[obj_id] = obj

    def get(self, owner, obj_id: str):
        with self._lock:
            objects = self._objects_of(owner, create=False)
            return None if objects is None else objects.get(obj_id)

    def drop(self, owner, obj_id: str) -> None:
        with self._lock:
            objects = self._objects_of(owner, create=False)
            if objects is not None:
                objects.pop(obj_id, None)
            self._forget(owner, obj_id)

    def record(self, owner, obj_id: str, size: int) -> None:
        with self._lock:
            if self.get(owner, obj_id) is None:
                return  # evicted meanwhile
            self.total_bytes += size - self._sizes.get((owner, obj_id), 0)
            self._sizes[(owner, obj_id)] = size

    def owner_bytes(self, owner) -> int:
        with self._lock:
            objects = self._owners._data.get(owner) or {}
            return sum(self._sizes.get((owner, obj_id), 0) for obj_id in objects)


_SHARED_SIZE_LEAVES = (type, ModuleType)
_BOUND_METHODS = (MethodType, BuiltinMethodType, MethodWrapperType)


def bounded_deep_sizeof(obj, limit: Optional[int] = None) -> int:
    """Approximate memory held by ``obj`` and everything it references (containers,
    instance ``__dict__`` and ``__slots__``, what a bound method, a ``partial`` or a
    function's closure, attributes and defaults hold), counting each object once. Stops
    as soon as the total exceeds ``limit``, so measuring costs at most about ``limit``
    bytes' worth of objects. Classes, modules and the code of functions are shared, so
    not counted, and neither is what classes and modules hold (class attributes, module
    globals), nor caches kept in C (``lru_cache``). Holding a bound method of another
    object counts that whole object, as holding the object itself would.

    >>> small, big = bounded_deep_sizeof([1, 2]), bounded_deep_sizeof(list(range(1000)))
    >>> small < big
    True
    >>> bounded_deep_sizeof(list(range(10**6)), limit=1000) > 1000
    True
    """
    seen, total, todo = set(), 0, deque([obj])
    while todo:
        o = todo.pop()
        if id(o) in seen or isinstance(o, _SHARED_SIZE_LEAVES):
            continue
        seen.add(id(o))
        try:
            held = _held_by_callable(o)
        except Exception:  # an exotic object (a mock, a proxy): measure it plainly
            held = None
        if isinstance(o, FunctionType):  # the code is shared; only what it holds counts
            todo.extend(held or ())
            continue
        todo.extend(held or ())
        total += sys.getsizeof(o, 0)
        if limit is not None and total > limit:
            break
        if isinstance(o, dict):
            todo.extend(o.keys())
            todo.extend(o.values())
        elif isinstance(o, (list, tuple, set, frozenset, deque)):
            todo.extend(o)
        try:  # a __getattr__ may raise anything
            todo.extend(_instance_state(o))
        except Exception:
            pass
    return total


def _instance_state(o):
    """An object's ``__dict__`` and the values of its ``__slots__``."""
    if hasattr(o, "__dict__") and isinstance(vars(o), dict):
        yield vars(o)
    for klass in type(o).__mro__:
        slots = getattr(klass, "__slots__", ())
        for slot in (slots,) if isinstance(slots, str) else slots:
            if slot not in ("__dict__", "__weakref__") and hasattr(o, slot):
                yield getattr(o, slot)


def _held_by_callable(o) -> Optional[list]:
    """What a function (closure, attributes, defaults), bound method, static or class
    method, or ``partial`` holds; ``None`` for anything else."""
    if isinstance(o, FunctionType):
        cells = [c.cell_contents for c in o.__closure__ or () if _cell_is_set(c)]
        return [*cells, o.__dict__, o.__defaults__, o.__kwdefaults__]
    if isinstance(o, MethodType):
        return [o.__self__, o.__func__]
    if isinstance(o, _BOUND_METHODS):  # a builtin's: what it is bound to
        return [o.__self__]
    if isinstance(o, (staticmethod, classmethod)):
        return [o.__func__]
    if isinstance(o, partial):
        return [o.func, o.args, o.keywords]
    return None


def _cell_is_set(cell) -> bool:
    try:
        cell.cell_contents
    except ValueError:  # an empty cell (a free variable not yet assigned)
        return False
    return True


def public_attr(obj, attr_name: str) -> bool:
    """The attribute policy ``attr_names='*'`` stands for: only public methods.

    A name is dispatchable if it does not start with ``_`` and

    - for a module: it is a function that the module defines (or lists in its
      ``__all__``), never something it merely imports, nor plain data;
    - otherwise: it is a plain Python function, ``staticmethod``,
      ``classmethod`` or ``property`` defined in the object's class (or a base
      class), and the instance does not shadow it.

    This keeps private helpers, dunders (``__dict__``, ``__init__``, ...),
    per-instance state (``__dict__`` entries, ``__slots__``, dataclass and
    namedtuple fields) and callables merely assigned as class attributes
    (``opener = open``) out of reach of HTTP clients.

    Note that every public method is exposed, inherited ones included (e.g. a
    pydantic model's ``model_dump``). For anything holding secrets, or a mapping
    whose mutators should stay private (``MutableMapping`` mixins such as
    ``clear`` and ``pop`` are plain functions), list the names explicitly instead.

    >>> class A:
    ...     data = 0
    ...     opener = open
    ...     def f(self): ...
    ...     def _g(self): ...
    ...     def __init__(self): self.secret = 1
    >>> [public_attr(A(), name)
    ...  for name in ('f', '_g', '__init__', '__dict__', 'secret', 'data', 'opener')]
    [True, False, False, False, False, False, False]
    """
    if not isinstance(attr_name, str) or attr_name.startswith("_"):
        return False
    if isinstance(obj, ModuleType):
        return _is_public_module_function(obj, attr_name)
    try:  # (bypassing any class-level ``__dict__`` attribute)
        instance_dict = object.__getattribute__(obj, "__dict__")
    except AttributeError:
        instance_dict = {}
    if attr_name in instance_dict:
        return False  # instance state, or an instance attribute shadowing a method
    # Look in the class's MRO dicts only (not the metaclass: ``mro``, ...), and at
    # the raw class attribute, not what the instance would return for it
    for klass in type(obj).__mro__:
        if attr_name in vars(klass):
            return _is_method_like(vars(klass)[attr_name])
    return False


def _is_method_like(class_attr) -> bool:
    if isinstance(class_attr, (staticmethod, classmethod)):
        class_attr = class_attr.__func__
    return isinstance(class_attr, (FunctionType, property))


def _is_public_module_function(module: ModuleType, attr_name: str) -> bool:
    value = vars(module).get(attr_name)
    if not inspect.isfunction(value):
        return False
    exported = getattr(module, "__all__", None)
    if exported is not None:
        return attr_name in exported
    return value.__module__ == module.__name__


def unsafe_any_attr(obj, attr_name: str) -> bool:
    """Dispatch ANY attribute of the object, including private ones and dunders.

    This was the behaviour of ``attr_names='*'`` before ``public_attr``: it lets a
    client read ``__dict__``, call ``__init__`` with arguments of its choosing, and so
    on. Use ``attr_names=unsafe_any_attr`` only when every client is trusted.
    """
    return isinstance(attr_name, str) and hasattr(obj, attr_name)


def _attr_name_policy(attr_names) -> Callable[[Any, str], bool]:
    """Normalize a handler's ``attr_names`` into a ``(obj, attr_name) -> bool``
    predicate: ``'*'`` means ``public_attr``, a callable is used as is, and an
    iterable of names is an explicit allow-list (dunders included, if listed).
    """
    if attr_names == "*":
        return public_attr
    if callable(attr_names):
        return attr_names
    if isinstance(attr_names, str):
        allowed = {attr_names}
    else:
        allowed = set(attr_names)
    return lambda obj, attr_name: (
        isinstance(attr_name, str) and attr_name in allowed and hasattr(obj, attr_name)
    )


def method_not_found(method_name):
    raise web.HTTPNotFound(
        text=json.dumps({"error": f"method {method_name} not found"}),
        content_type=JSON_CONTENT_TYPE,
    )


# default TypeAsserter used in this project
assert_type = TypeAsserter(
    types_for_kind={
        "input_mapper": Callable,
        "output_mapper": Callable,
    }
)


def func_copy(func) -> Callable:
    new_func = FunctionType(
        func.__code__,
        func.__globals__,
        func.__name__,
        func.__defaults__,
        func.__closure__,
    )
    new_func.__dict__.update(deepcopy(func.__dict__))
    return new_func


def mk_route(func, **configs):
    """
    Generate a route object and an OpenAPI path specification for a function

    :param func: The function

    :Keyword Arguments: The configuration settings
    """

    def get_input_args_and_kwargs(inputs):
        input_args = ()
        input_kwargs = {}
        if isinstance(inputs, dict):
            input_kwargs = inputs
        elif isinstance(inputs, list):
            input_args = tuple(inputs)
        elif isinstance(inputs, tuple):
            input_args = inputs[0]
            input_kwargs = inputs[1]
        return input_args, input_kwargs

    # TODO: perhaps collections.abc.Mapping initialized with func, configs, etc.
    config_for = partial(
        mk_config, func=func, configs=configs, defaults=default_configs
    )
    framework = _get_framework(configs, default_configs)
    input_mapper = config_for("input_mapper")
    output_mapper = config_for("output_mapper")
    error_handler = config_for("error_handler")
    header_inputs = config_for("header_inputs", type=dict)
    logger = config_for("logger")

    exclude_request_keys = header_inputs.keys()
    request_schema = getattr(input_mapper, "request_schema", None)
    if request_schema is None or input_mapper.__name__ == default_input_mapper.__name__:
        request_schema = mk_input_schema_from_func(
            func, exclude_keys=exclude_request_keys
        )
    request_content_type = getattr(input_mapper, "content_type", DFLT_CONTENT_TYPE)
    response_schema = getattr(
        output_mapper,
        "response_schema",
        mk_output_schema_from_func(output_mapper),
    )
    if not response_schema:
        response_schema = getattr(
            func, "response_schema", mk_output_schema_from_func(func)
        )
    response_content_type = getattr(output_mapper, "content_type", DFLT_CONTENT_TYPE)

    def handle_error(func):
        def handle_request(req):
            if logger:
                logger.debug(f"Handling {http_method.upper()} {path}")
            try:
                return func(req)
            except (DataError, AuthorizationError, InputError) as error:
                if logger:
                    level = (
                        logging.INFO
                        if logger.getEffectiveLevel() >= logging.INFO
                        else logging.DEBUG
                    )
                    exc_info = level == logging.DEBUG
                    logger.log(level, traceback.format_exc(), exc_info=exc_info)
                else:
                    print(traceback.format_exc())
                return error_handler(error)
            except Exception as error:
                print(traceback.format_exc())
                if logger:
                    logger.exception(error)
                return error_handler(error)

        return handle_request

    @handle_error
    def sync_handle_request(req):
        token = current_request.set(req)
        try:
            inputs = input_mapper(req)
            input_args, input_kwargs = get_input_args_and_kwargs(inputs)
            raw_result = call_with_inputs(func, input_args, input_kwargs)
            return output_mapper(raw_result, **inputs)
        finally:
            current_request.reset(token)

    @handle_error
    async def aiohttp_handle_request(req):
        token = current_request.set(req)
        try:
            return await _aiohttp_handle(req)
        finally:
            current_request.reset(token)

    async def _aiohttp_handle(req):
        inputs = input_mapper(req)
        if isawaitable(inputs):  # Pattern: pass-on async property
            inputs = await inputs
        input_args, input_kwargs = get_input_args_and_kwargs(inputs)
        raw_result = call_with_inputs(func, input_args, input_kwargs)
        if isawaitable(raw_result):  # Pattern: pass-on async property
            raw_result = await raw_result
        final_result = output_mapper(raw_result, **inputs)
        if isawaitable(final_result):
            final_result = await final_result
        if not isinstance(final_result, web.Response):
            final_result = web.json_response(final_result)
        return final_result

    #  TODO: Align config keys and variable names
    valid_http_methods = {"get", "put", "post", "delete"}  # outside function
    http_method = config_for("http_method")  # read
    assert isinstance(http_method, str)  # validation
    http_method = http_method.lower()  # normalization
    assert http_method in valid_http_methods  # validation

    def mk_framework_route(http_method, path, method_name):
        if framework == AIOHTTP:
            web_mk_route = getattr(web, http_method)
            return web_mk_route(path, aiohttp_handle_request)
        else:
            if framework == FLASK:
                from flask import request
            elif framework == BOTTLE:
                from bottle import request

            def handle_request(*args):
                result = sync_handle_request(request)
                if isawaitable(result):
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    result = loop.run_until_complete(result)
                return result

            handle_request.path = path
            handle_request.http_method = http_method
            handle_request.method_name = method_name
            return handle_request

    # TODO: Make func -> path a function (not hardcoded)
    # TODO: Make sure that func -> path MAPPING is known outside (perhaps through openapi)
    method_name = config_for("name") or func.__name__
    path = config_for("route") or f"/{method_name}"

    route = mk_framework_route(http_method, path, method_name)

    extra_path_info = {"description": func.__doc__ or ""}
    path_fields = dict({"x-method_name": method_name}, **extra_path_info)
    openapi_path = mk_openapi_path(
        path,
        http_method,
        request_schema=request_schema,
        request_content_type=request_content_type,
        response_schema=response_schema,
        response_content_type=response_content_type,
        path_fields=path_fields,
    )

    return route, openapi_path


def mk_routes_and_openapi_specs(funcs, **configs):
    routes = []
    get_config = partial(
        mk_config, func=None, configs=configs, defaults=default_configs
    )
    openapi_config = get_config("openapi", type=dict)
    if "base_url" not in openapi_config:
        host = get_config("host")
        port = get_config("port")
        protocol = "https" if port == 443 else "http"
        openapi_config["base_url"] = f"{protocol}://{host}:{port}"
    openapi_spec = mk_openapi_template(openapi_config)
    header_inputs = get_config("header_inputs")
    if header_inputs:
        openapi_spec["x-header-inputs"] = header_inputs
    for func in funcs:
        route, openapi_path = mk_route(func, **configs)
        routes.append(route)
        add_paths_to_spec(openapi_spec["paths"], openapi_path)
    openapi_filename = openapi_config.get("filename", None)
    if openapi_filename:
        with open(openapi_filename, "w") as fp:
            json.dump(openapi_spec, fp)
    return routes, openapi_spec


Handlers = Iterable[
    Union[
        Callable,
        TypedDict(
            "HandlerWithMappers",
            endpoint=Callable,
            input_mapper=Optional[Callable],
            output_mapper=Optional[Callable],
        ),
    ]
]
SubAppSpec = TypedDict(
    "SubAppSpec",
    handlers=Handlers,
    config=Dict[str, Any],
)
AppSpec = Union[Handlers, Dict[str, Union[Handlers, SubAppSpec]]]


def mk_flask_app(funcs, **configs):
    from flask import Flask

    routes, openapi_spec = mk_routes_and_openapi_specs(funcs, **configs)
    app_name = mk_config("app_name", None, configs, default_configs)
    app = Flask(app_name)
    middleware = mk_config("middleware", None, configs, default_configs)
    # publish_openapi = mk_config('publish_openapi', None, configs, default_configs)
    if middleware:
        app = middleware(app)
    for route in routes:
        app.add_url_rule(
            route.path,
            route.method_name,
            route,
            methods=[route.http_method.upper()],
        )
    app.add_url_rule("/ping", "ping", lambda: {"ping": "pong"})
    app.add_url_rule("/openapi", "openapi", lambda: openapi_spec)
    app.openapi_spec = openapi_spec
    return app


def mk_bottle_app(funcs, **configs):
    from bottle import Bottle

    routes, openapi_spec = mk_routes_and_openapi_specs(funcs, **configs)
    app = Bottle(catchall=False)
    enable_cors = mk_config("enable_cors", None, configs, default_configs)
    plugins = mk_config("plugins", None, configs, default_configs)
    if enable_cors:
        cors_allowed_origins = mk_config(
            "cors_allowed_origins", None, configs, default_configs
        )
        app.install(CorsPlugin(cors_allowed_origins))
    publish_openapi = mk_config("publish_openapi", None, configs, default_configs)
    openapi_insecure = mk_config("openapi_insecure", None, configs, default_configs)
    publish_swagger = mk_config("publish_swagger", None, configs, default_configs)
    if plugins:
        for plugin in plugins:
            app.install(plugin)
    for route in routes:
        route_http_method = route.http_method.upper()
        http_methods = (
            route.http_method if not enable_cors else [OPTIONS, route_http_method]
        )
        # print(f'Mounting route: {route.path} {route.http_method.upper()}')
        app.route(route.path, http_methods, route, route.method_name)
    app.route(
        path="/ping", callback=lambda: {"ping": "pong"}, name="ping", skip=plugins
    )
    if publish_openapi:
        skip = plugins if openapi_insecure else None
        app.route(
            path="/openapi",
            callback=lambda: openapi_spec,
            name="openapi",
            skip=skip,
        )
    app.openapi_spec = openapi_spec
    if publish_swagger:
        swagger_url = mk_config("swagger_url", None, configs, default_configs)
        swagger_title = mk_config("swagger_title", None, configs, default_configs)
        api_doc(
            app,
            config_spec=json.dumps(openapi_spec),
            url_prefix=swagger_url,
            title=swagger_title,
        )
    return app


def mk_aiohttp_app(funcs, **configs):
    routes, openapi_spec = mk_routes_and_openapi_specs(funcs, **configs)
    middleware = mk_config("middleware", None, configs, default_configs)
    app = web.Application(middlewares=middleware)
    app.add_routes(
        [
            web.get("/ping", lambda: web.json_response({"ping": "pong"}), name="ping"),
            web.get(
                "/openapi", lambda: web.json_response(openapi_spec), name="openapi"
            ),
            *routes,
        ]
    )
    # adding a few more attributes
    app.openapi_spec = openapi_spec
    return app


@Sig.add_optional_keywords(default_configs)
def mk_app(app_spec: AppSpec, **configs):
    """
    Generates an application which exposes web services created from the given python
    functions to remotely run them.
    You can generate a multi-service application defining a route per API or sub
    application.

    First define a bunch of functions (or handlers) you want to expose as a web service.

    >>> def foo():
    ...     return 0
    ...
    >>> def bar():
    ...     return True
    ...

    Let's make a single-service application. A single API will be generated with an
    endpoint per handler, plus an auto-generated enpoints to ping the API.

    >>> handlers = [foo, bar]
    >>> app = mk_app(handlers)
    >>> app.get_url('bar')
    '/bar'
    >>> app.get_url('foo')
    '/foo'
    >>> app.get_url('ping')
    '/ping'

    You can also automatically generate an endpoint to expose the openapi specification
    of your API by activating the flag "publish_openapi". Publishing the openapi
    specification will allow a client application to use the specification object to
    build an interface to actually consume the API by wrapping the http layer.

    >>> app = mk_app(handlers, publish_openapi=True)
    >>> app.openapi_spec # doctest: +NORMALIZE_WHITESPACE
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

    You can also generate swagger documentation by activating the "publish_swagger"
    flag. This will generate a swagger documentation for the API and make it available
    at the specified url (by default "/swagger").

    >>> app = mk_app(handlers, publish_openapi=True, publish_swagger=True)

    Let's use http2py to consume the openapi specification

    >>> from http2py import HttpClient
    >>> api = HttpClient(openapi_spec=app.openapi_spec)
    >>> assert(hasattr(api, 'foo'))
    >>> assert(hasattr(api, 'bar'))

    Now, let's make a multi-service application. You only have to define a route per
    API with a list of handlers for each API.

    >>> handler_spec = {
    ...     'foo_api': [foo],
    ...     'bar_api': [bar],
    ... }
    >>> app = mk_app(handler_spec, publish_openapi=True)
    >>> app.get_url('/foo_api')
    '/foo_api'
    >>> app.get_url('/bar_api')
    '/bar_api'

    :param handler_spec: The handler specification. Can be a list of python to expose,
    or a dict with a list of functions to expose per route in case of a multi-service
    application.
    :type handler_spec: HandlerSpec
    :param **configs: The configuration for the application. See config.yaml for
    configuration documentation.
    :type **configs: dict
    """

    def mk_single_api_app():
        def add_mappers_to_config():
            handlers_with_mappers = [x for x in app_spec if isinstance(x, dict)]
            input_mappers = {}
            output_mappers = {}
            for handler in handlers_with_mappers:
                endpoint = handler["endpoint"]
                input_mapper = handler.get("input_mapper")
                endpoint_name = handler.get("name", name_of_obj(endpoint))
                if input_mapper:
                    input_mappers[endpoint_name] = input_mapper
                output_mapper = handler.get("output_mapper")
                if output_mapper:
                    output_mappers[endpoint_name] = output_mapper
            if input_mappers:
                app_configs["input_mapper"] = input_mappers
            if output_mappers:
                app_configs["output_mapper"] = output_mappers

        def gen_handlers():
            for handler in app_spec:
                if isinstance(handler, dict):
                    yield _get_func_to_dispatch_handler(handler)
                else:
                    yield handler

        app_configs = dict(configs)
        handlers = list(gen_handlers())
        # print(f"{app_spec=}\n{handlers}")
        add_mappers_to_config()
        if framework == FLASK:
            return mk_flask_app(handlers, **app_configs)
        if framework == BOTTLE:
            return mk_bottle_app(handlers, **app_configs)
        return mk_aiohttp_app(handlers, **app_configs)

    def mk_multi_api_app():
        def get_web_framework_objects():
            if framework == BOTTLE:
                app = Bottle(catchall=False)
                return app, app.mount
            elif framework == AIOHTTP:
                app = web.Application()
                return app, app.add_subapp
            return None

        parent_app, add_subapp_meth = get_web_framework_objects()
        for route, route_spec in app_spec.items():
            # bottle (>=0.13) and aiohttp both require mount prefixes to start with '/'
            route = route if route.startswith("/") else "/" + route
            if isinstance(route_spec, dict):
                handlers = route_spec["handlers"]
                subapp_configs = route_spec["config"]
            else:
                handlers = route_spec
                subapp_configs = deepcopy(configs)
            if "openapi" not in subapp_configs:
                subapp_configs["openapi"] = {}
            if "base_url" not in subapp_configs["openapi"]:
                get_config = partial(
                    mk_config, func=None, configs=configs, defaults=default_configs
                )
                host = get_config("host")
                port = get_config("port")
                protocol = "https" if port == 443 else "http"
                subapp_configs["openapi"]["base_url"] = f"{protocol}://{host}:{port}"
            subapp_configs["openapi"]["base_url"] = (
                subapp_configs["openapi"]["base_url"] + route
            )
            subapp = mk_app(handlers, **subapp_configs)
            add_subapp_meth(route, subapp)
        return parent_app

    framework = _get_framework(configs, default_configs)
    if isinstance(app_spec, dict):
        return mk_multi_api_app()
    return mk_single_api_app()


@Sig.add_optional_keywords(default_configs)
def run_app(app_obj: Union[AppSpec, Any], **configs):
    """
    Run an application which exposes web services created from the given python
    functions to remotely run them.
    You can generate a multi-service application defining a route per api or sub
    application.
    You can also generate the application first, then run it using this function.

    :param app_obj: The handler specification or application object. Can be a list of
    python to expose, or a dict with a list of functions to expose per route in case
    of a multi-service. Can also be a pre-generated application object to run.
    :type handler_spec: Union[HandlerSpec, Any]
    :param **configs: The configuration for the application. See
    `py2http.default_configs:default_configs` for defaults and config.yaml for
    configuration documentation.
    :type **configs: dict
    """

    def get_run_func():
        framework = _get_framework(configs, default_configs)
        if framework == BOTTLE:
            return run_bottle
        elif framework == AIOHTTP:
            return web.run_app
        raise NotImplementedError("")

    if isinstance(app_obj, Iterable):
        app = mk_app(app_obj, **configs)
        run_app(app, **configs)
    else:
        run_func = get_run_func()
        get_config = partial(
            mk_config, func=None, configs=configs, defaults=default_configs
        )
        host = get_config("host")
        port = get_config("port")
        server = get_config("server")
        ssl_certfile = get_config("ssl_certfile")
        ssl_keyfile = get_config("ssl_keyfile")

        # run_func(app_obj, host=host, port=port, ssl_context=ssl_context, server='gunicorn')
        run_func(
            app_obj,
            host=host,
            port=port,
            server=server,
            certfile=ssl_certfile,
            keyfile=ssl_keyfile,
        )


def _get_framework(configs, default_configs):
    framework = mk_config("framework", None, configs, default_configs)
    # NOTE Only support Bottle until we redesign py2http using a reusable tool for routing
    # if framework not in (FLASK, BOTTLE, AIOHTTP):
    if framework != BOTTLE:
        raise NotImplementedError(
            f'The Web Framework "{framework}" is not supported by py2http'
        )
    os.environ["PY2HTTP_FRAMEWORK"] = framework
    return framework


def _get_func_to_dispatch_handler(handler):
    endpoint = handler.get("endpoint")
    if endpoint is None:
        raise InputError("No endpoint found in handler")
    name = handler.get("name", name_of_obj(endpoint))
    if not name:
        raise InputError("No way to determine name of handler")
    attr_names = handler.get("attr_names")
    if attr_names is None:
        # TODO: This is a hack! Address the problem in a cleaner way.
        #   This hack is just completing some unclean handling of names already present
        #   in the code. At the end of this function there's a func.__name__ = name,
        #   but this operation was forgotten here. That said, we shouldn't do this at
        #   all.
        #   --> When a function is specified for a handler, the long language specs
        #   needs to be created from it, and subsequently, the "name" field, not the
        #   __name__ attribute, needs to be used.
        endpoint.__name__ = name  # the hack
        return endpoint
        # was return endpoint, but then the output didn't get the __name__ = name
        # func = endpoint
    is_dispatchable = _attr_name_policy(attr_names)
    if inspect.isclass(endpoint):
        func = _class_endpoint_dispatcher(endpoint, handler, name, is_dispatchable)

    elif isinstance(endpoint, ModuleType):  # a module's functions: no shared object

        def func(_attr_name=None, **kwargs):
            return _get_attr_value(endpoint, _attr_name, is_dispatchable, **kwargs)

    else:
        func = _instance_endpoint_dispatcher(endpoint, handler, name, is_dispatchable)

    func.__name__ = name
    return func


class _MappingObjStore:
    """``OwnedObjStore``'s interface over a user-given ``obj_store`` mapping
    (``shared_objects`` mode): one owner, no byte accounting, a lock around access."""

    total_bytes = 0

    def __init__(self, mapping: MutableMapping):
        self._mapping, self._lock = mapping, threading.RLock()

    def put(self, owner, obj_id, obj):
        with self._lock:
            self._mapping[obj_id] = obj

    def get(self, owner, obj_id):
        with self._lock:
            return self._mapping.get(obj_id)

    def drop(self, owner, obj_id):
        with self._lock:
            self._mapping.pop(obj_id, None)

    def record(self, owner, obj_id, size):
        pass

    def owner_bytes(self, owner):
        return 0


_SHARED_OWNER = "<shared>"


def _request_owner(owner_of: ObjOwner, name: str) -> Callable[[], Any]:
    """A zero-argument function giving the owner of the request being handled, as
    ``owner_of(current_request)`` says, refusing requests it does not identify."""
    if not callable(owner_of):
        raise TypeError(f"obj_owner must be callable or shared_objects: {owner_of!r}")

    def owner():
        who = owner_of(current_request.get())
        if who is None or who == "":
            raise AuthorizationError(f"{name}: no owner for this request")
        try:
            hash(who)
        except TypeError:
            raise TypeError(
                f"obj_owner of {name!r} must return a hashable, got {type(who)}"
            ) from None
        return who

    return owner


def _instance_endpoint_dispatcher(obj, handler, name, is_dispatchable):
    """The function behind an instance endpoint (``handler['endpoint']`` is an object,
    not a class or module): it dispatches ``_attr_name`` on that one object, which every
    client allowed in shares. A method that mutates it (``__setitem__``, ``write``...)
    lets each of them change what the others see.

    Handler options:

    - ``obj_owner`` (required): ``(request) -> owner`` (see ``ObjOwner``); a request it
      does not identify is refused, the others share the object. Or ``shared_objects``
      to let any client use it. An instance endpoint without one is refused at build
      time.
    - ``max_obj_size`` (``DFLT_MAX_OBJ_SIZE``) and ``obj_sizeof``
      (``bounded_deep_sizeof``): the bytes the object may hold, measured when the
      service is built (an object already over it is refused then) and after every
      dispatched call, failed ones included. The call that takes it over the limit has
      already run: its result is withheld, the object is kept, and every later call is
      refused until it is back under, except calls to ``obj_shrinkers``. So memory is
      bounded by the limit plus what the calls running at that moment allocate.
      ``None`` disables the check. Raise ``max_obj_size``, or pass an ``obj_sizeof``
      that skips what is not request-driven (a loaded model, a database connection),
      for a large object. Not measured: data the object keeps outside the process
      (files, a database), and state held in its class or in module globals.
      Measuring walks the object (up to ``max_obj_size`` bytes of it) after every
      call, reads included, so a large limit costs time on every request. A method
      returning a generator or coroutine does its work after the measure: what it
      adds is caught by the next call.
    - ``obj_shrinkers``: names of dispatched attributes that only ever remove
      (``pop``, ``clear``, ``__delitem__`` if ``attr_names`` lists it...), still
      callable while the object is over its limit so a client can bring it back under.
      Empty by default: py2http cannot tell which methods shrink an object, and the
      bound holds only if every name listed really only removes (one that also adds is
      never refused).
    """
    owner_of = handler.get("obj_owner")
    if owner_of is None:
        raise ValueError(
            f"Instance endpoint {name!r} is one object shared by every client: give it "
            "an obj_owner, a callable (request) -> owner (e.g. the authenticated user "
            "id) that refuses requests it does not identify, or obj_owner=shared_objects "
            "(from py2http.service) to let any client use it, as before."
        )
    owner = (
        (lambda: None) if owner_of is shared_objects else _request_owner(owner_of, name)
    )
    max_obj_size = handler.get("max_obj_size", DFLT_MAX_OBJ_SIZE)
    sizeof = handler.get("obj_sizeof", bounded_deep_sizeof)

    def is_too_big():
        return max_obj_size is not None and sizeof(obj, max_obj_size) > max_obj_size

    if is_too_big():
        raise ValueError(
            f"Instance endpoint {name!r} already holds more than max_obj_size="
            f"{max_obj_size} bytes (as measured by obj_sizeof): raise max_obj_size, pass "
            "an obj_sizeof that skips what clients cannot grow, or max_obj_size=None."
        )
    shrinkers = handler.get("obj_shrinkers", ())
    if isinstance(shrinkers, str):
        raise TypeError(f"obj_shrinkers must be a collection of names: {shrinkers!r}")
    shrinkers = frozenset(shrinkers)
    for attr_name in shrinkers:
        if not is_dispatchable(obj, attr_name):
            raise ValueError(
                f"obj_shrinkers of {name!r}: {attr_name!r} is not dispatched "
                "(see attr_names)"
            )
    over_limit = threading.Event()  # set while the object is known to be too big
    measuring = threading.Lock()  # so a stale measure cannot clear a newer one's flag

    def measure() -> bool:
        """Whether the object is over its limit, recorded in ``over_limit``."""
        with measuring:
            too_big = is_too_big()
            if too_big:
                over_limit.set()
            else:
                over_limit.clear()
            return too_big

    def refuse():
        allowed = f" (except {', '.join(sorted(shrinkers))})" if shrinkers else ""
        raise InputError(
            f"{name} is over its size limit ({max_obj_size} bytes): calls{allowed} "
            "are refused until it is back under"
        )

    def func(_attr_name=None, **kwargs):
        owner()
        shrinking = isinstance(_attr_name, str) and _attr_name in shrinkers
        if over_limit.is_set() and measure() and not shrinking:
            refuse()
        try:
            return _get_attr_value(obj, _attr_name, is_dispatchable, **kwargs)
        finally:  # a call that grows the object and then raises is measured too
            # a shrinker that ran but left it over the limit keeps its result
            if measure() and not shrinking:
                refuse()

    return func


def _class_endpoint_dispatcher(cls, handler, name, is_dispatchable):
    """The function behind a class endpoint: called without ``_obj_id`` it creates an
    object and returns its id; with one, it dispatches ``_attr_name`` on that object.

    Handler options:

    - ``obj_owner`` (required): ``(request) -> owner`` (see ``ObjOwner``), binding each
      object to the client that created it (another owner's id is simply not found), or
      ``shared_objects`` to let anyone holding an id use it. A class endpoint without
      one is refused at build time.
    - ``obj_quota``: objects kept per owner (``DFLT_OBJ_QUOTA``); an owner's least
      recently used object is evicted beyond it. ``max_owners`` bounds the owners.
    - ``obj_store``: ``shared_objects`` mode only, an id -> object mapping replacing the
      default store (``DFLT_OBJ_STORE_MAX_SIZE`` objects); byte budgets other than
      ``max_obj_size`` are then not tracked.
    - ``max_obj_size`` (``DFLT_MAX_OBJ_SIZE``), ``max_owner_bytes``
      (``DFLT_MAX_OWNER_BYTES``) and ``max_total_bytes`` (``DFLT_MAX_TOTAL_BYTES``):
      bytes one object, all of one owner's objects, and all objects of the endpoint may
      hold. Sizes come from ``obj_sizeof`` (default ``bounded_deep_sizeof``, which
      stops at ``max_obj_size``, so measuring costs at most about that much), measured
      after creation and after every dispatched call, failed ones included. The object
      that takes a budget over it is dropped. ``None`` disables a budget. An object
      referencing large shared data (a loaded model) counts that data: raise
      ``max_obj_size`` or pass an ``obj_sizeof`` that skips it. A single call can still
      allocate before it is measured.
    """
    owner_of = handler.get("obj_owner")
    if owner_of is None:
        raise ValueError(
            f"Class endpoint {name!r} needs an obj_owner: a callable (request) -> owner "
            "(e.g. the authenticated user id), so a client can only use the objects it "
            "created. Pass obj_owner=shared_objects (from py2http.service) to let any "
            "client holding an object id use the object, as before."
        )
    max_obj_size = handler.get("max_obj_size", DFLT_MAX_OBJ_SIZE)
    max_owner_bytes = handler.get("max_owner_bytes", DFLT_MAX_OWNER_BYTES)
    max_total_bytes = handler.get("max_total_bytes", DFLT_MAX_TOTAL_BYTES)
    sizeof = handler.get("obj_sizeof", bounded_deep_sizeof)

    if owner_of is shared_objects:
        custom = handler.get("obj_store")
        store = (
            OwnedObjStore(quota=DFLT_OBJ_STORE_MAX_SIZE, max_owners=1)
            if custom is None
            else _MappingObjStore(custom)
        )

        def owner():
            return _SHARED_OWNER

    else:
        owner = _request_owner(owner_of, name)
        if handler.get("obj_store") is not None:
            raise ValueError(
                "obj_store applies to obj_owner=shared_objects only; with an obj_owner "
                "use obj_quota and max_owners."
            )
        store = OwnedObjStore(
            quota=handler.get("obj_quota", DFLT_OBJ_QUOTA),
            max_owners=handler.get("max_owners", DFLT_MAX_OWNERS),
        )

    def over_budget(who, obj_id, obj):
        """Why the object must go, or None. Records its size when it may stay."""
        limit = max_obj_size
        size = sizeof(obj, limit) if limit is not None else sizeof(obj, None)
        if limit is not None and size > limit:
            return f"grew past the size limit ({limit} bytes)"
        store.record(who, obj_id, size)
        if max_owner_bytes is not None and store.owner_bytes(who) > max_owner_bytes:
            return f"takes its owner past {max_owner_bytes} bytes"
        if max_total_bytes is not None and store.total_bytes > max_total_bytes:
            return f"takes the endpoint past {max_total_bytes} bytes"
        return None

    def check_size(who, obj_id, obj):
        no_budget = max_obj_size is max_owner_bytes is max_total_bytes is None
        reason = None if no_budget else over_budget(who, obj_id, obj)
        if reason is not None:
            store.drop(who, obj_id)
            raise InputError(f"Object {obj_id} {reason} and was dropped")

    def func(_obj_id=None, _attr_name=None, **kwargs):
        who = owner()
        if _obj_id is None:
            if _attr_name is not None:
                raise InputError("_attr_name must be None when _obj_id is None")
            new_obj = call_with_inputs(cls, kwargs=kwargs)
            new_id = str(uuid4())
            store.put(who, new_id, new_obj)
            check_size(who, new_id, new_obj)
            return new_id
        obj = store.get(who, _obj_id) if isinstance(_obj_id, str) else None
        if obj is None:
            raise InputError(f"No object found with id {_obj_id}")
        if _attr_name is None:
            raise InputError("_attr_name must be provided when _obj_id is not None")
        try:
            return _get_attr_value(obj, _attr_name, is_dispatchable, **kwargs)
        finally:  # a call that grows the object and then raises is measured too
            check_size(who, _obj_id, obj)

    return func


def _get_attr_value(obj, attr_name, is_dispatchable, /, **kwargs):
    if not is_dispatchable(obj, attr_name):
        raise InputError(
            f"No attribute found with name {attr_name} or it is not dispatched"
        )
    attr = getattr(obj, attr_name)
    if callable(attr):
        return call_with_inputs(attr, kwargs=kwargs)
    return attr
