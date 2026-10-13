"""Dispatching HTTP requests to the attributes of objects, classes and modules.

A handler whose ``endpoint`` is not a function names the attributes clients may call
with ``attr_names`` (see ``public_attr`` for ``'*'``):

- a **module**: its functions are called by name. They are function endpoints like
  any other: no object is kept, so there is no size bound, and a function that mutates
  module globals does so for every client, exactly as a plain function endpoint (or a
  bound method passed into an app spec) would. Authenticate with the auth middleware
  (``mk_jwt_middleware``, ``JWTPlugin``), or pass an optional ``obj_owner`` to refuse
  requests it does not identify;
- an **instance** (one object every client shares): ``_instance_endpoint_dispatcher``;
- a **class** (each client creates and uses its own objects):
  ``_class_endpoint_dispatcher``.

Instances and classes need an ``obj_owner``, a ``(request) -> owner`` hook reading
``current_request``, and are bounded in size (``py2http.sizeof``), measured after each
call except those to ``obj_readers``. A call returning a generator, coroutine or async
generator is measured when that result finishes, not when it is returned.
"""

import inspect
import threading
from collections import OrderedDict
from collections.abc import MutableMapping
from contextvars import ContextVar
from types import FunctionType, ModuleType
from typing import Any, Callable, Optional
from uuid import uuid4

from i2 import name_of_obj
from i2.errors import AuthorizationError, InputError

from py2http.sizeof import bounded_deep_sizeof
from py2http.util import call_with_inputs

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


def _at_least_one(name: str, value: int) -> int:
    if value < 1:
        raise ValueError(f"{name} must be at least 1, got {value}")
    return value


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
        self.max_size = _at_least_one("max_size", max_size)
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

    def peek(self, k, default=None):
        """``self.get(k, default)``, without making ``k`` the most recently used."""
        return self._data.get(k, default)

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
        _at_least_one("max_owners", max_owners)
        self._quota = _at_least_one("quota", quota)
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
            objects = self._owners.peek(owner) or {}
            return sum(self._sizes.get((owner, obj_id), 0) for obj_id in objects)


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
        owner_of = handler.get("obj_owner")
        if owner_of is None or owner_of is shared_objects:
            owner = lambda: None  # noqa: E731
        else:
            owner = _request_owner(owner_of, name)

        def func(_attr_name=None, **kwargs):
            owner()  # an optional gate: refuses requests the hook does not identify
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
      call except those to ``obj_readers``, so a large limit costs time on each such
      request. A method returning a generator, coroutine or async generator is
      measured when that result finishes.
    - ``obj_readers``: names of dispatched attributes that never add to the object
      (``read``, ``__getitem__``, ``keys``...): calls to them are not measured, which
      saves the walk on every read. Empty by default; the bound holds only if every
      name listed really never adds (what one does add is caught by the next measured
      call).
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
    shrinkers = _names_option(handler, "obj_shrinkers", obj, name, is_dispatchable)
    readers = _names_option(handler, "obj_readers", obj, name, is_dispatchable)
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

        def call():
            return _get_attr_value(obj, _attr_name, is_dispatchable, **kwargs)

        if isinstance(_attr_name, str) and _attr_name in readers:
            return call()

        def settle():
            # a shrinker that ran but left it over the limit keeps its result
            if measure() and not shrinking:
                refuse()

        return _call_then_settle(call, settle)

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
      allocate before it is measured. A method returning a generator, coroutine or
      async generator is measured when that result finishes.
    - ``obj_readers``: names of methods that never add to an object; calls to them are
      not measured (see ``_instance_endpoint_dispatcher``).
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
    readers = handler.get("obj_readers", ())
    if isinstance(readers, str):
        raise TypeError(f"obj_readers must be a collection of names: {readers!r}")
    readers = frozenset(readers)
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
        size = sizeof(obj, max_obj_size)
        if max_obj_size is not None and size > max_obj_size:
            return f"grew past the size limit ({max_obj_size} bytes)"
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

        def call():
            return _get_attr_value(obj, _attr_name, is_dispatchable, **kwargs)

        if isinstance(_attr_name, str) and _attr_name in readers:
            return call()
        return _call_then_settle(call, lambda: check_size(who, _obj_id, obj))

    return func


def _names_option(handler, option, obj, name, is_dispatchable) -> frozenset:
    """A handler option naming dispatched attributes, validated."""
    names = handler.get(option, ())
    if isinstance(names, str):
        raise TypeError(f"{option} must be a collection of names: {names!r}")
    names = frozenset(names)
    for attr_name in names:
        if not is_dispatchable(obj, attr_name):
            raise ValueError(
                f"{option} of {name!r}: {attr_name!r} is not dispatched (see attr_names)"
            )
    return names


def _settled(result, settle: Callable[[], None]):
    """``result``, with ``settle()`` run once its work is done: now for a plain value,
    when it finishes for a generator, coroutine or async generator (which do their work
    after being returned)."""
    if inspect.isgenerator(result):

        def settling_generator():
            try:
                return (yield from result)
            finally:
                settle()

        return settling_generator()
    if inspect.iscoroutine(result):

        async def settling_coroutine():
            try:
                return await result
            finally:
                settle()

        return settling_coroutine()
    if inspect.isasyncgen(result):

        async def settling_async_generator():
            try:
                async for item in result:
                    yield item
            finally:
                settle()

        return settling_async_generator()
    settle()
    return result


def _call_then_settle(call: Callable[[], Any], settle: Callable[[], None]):
    """``call()``, then ``settle()`` (see ``_settled``); also after a call that raised,
    since it may have grown the object first."""
    try:
        result = call()
    except BaseException:
        settle()
        raise
    return _settled(result, settle)


def _get_attr_value(obj, attr_name, is_dispatchable, /, **kwargs):
    if not is_dispatchable(obj, attr_name):
        raise InputError(
            f"No attribute found with name {attr_name} or it is not dispatched"
        )
    attr = getattr(obj, attr_name)
    if callable(attr):
        return call_with_inputs(attr, kwargs=kwargs)
    return attr
