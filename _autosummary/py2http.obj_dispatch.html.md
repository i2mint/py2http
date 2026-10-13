# py2http.obj_dispatch

Dispatching HTTP requests to the attributes of objects, classes and modules.

A handler whose `endpoint` is not a function names the attributes clients may call
with `attr_names` (see `public_attr` for `'*'`):

- a **module**: its functions are called by name;
- an **instance** (one object every client shares): `_instance_endpoint_dispatcher`;
- a **class** (each client creates and uses its own objects):
  `_class_endpoint_dispatcher`.

Instances and classes need an `obj_owner`, a `(request) -> owner` hook reading
`current_request`, and are bounded in size (`py2http.sizeof`).

### Module Attributes

| [`current_request`](#py2http.obj_dispatch.current_request)   | The request being handled (set around every handler call), so per-request hooks such as `obj_owner` can read it without the dispatched function taking it.   |
|--------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------|
| [`ObjOwner`](#py2http.obj_dispatch.ObjOwner)          | `(request) -> owner`, a hashable that identifies an *authenticated* client (e.g. a user id from a verified token).                                           |

### Functions

| [`public_attr`](#py2http.obj_dispatch.public_attr)(obj, attr_name)     | The attribute policy `attr_names='*'` stands for: only public methods.    |
|----------------------------------------------------------------------------------|---------------------------------------------------------------------------|
| [`unsafe_any_attr`](#py2http.obj_dispatch.unsafe_any_attr)(obj, attr_name) | Dispatch ANY attribute of the object, including private ones and dunders. |

### Classes

| [`LRUObjStore`](#py2http.obj_dispatch.LRUObjStore)(\*[, max_size, on_evict])   | A mapping that keeps at most `max_size` items, evicting the least recently used one when a new key would exceed it (`on_evict(k, v)` is told).   |
|------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------|
| [`OwnedObjStore`](#py2http.obj_dispatch.OwnedObjStore)(\*[, quota, max_owners])  | Objects kept per owner, with object and byte budgets.                                                                                            |

### *class* py2http.obj_dispatch.LRUObjStore(, max_size=1000, on_evict=None)

Bases: [`MutableMapping`](https://docs.python.org/3/library/collections.abc.html#collections.abc.MutableMapping)

A mapping that keeps at most `max_size` items, evicting the least recently
used one when a new key would exceed it (`on_evict(k, v)` is told).

Used as the default store of objects created through a class endpoint, so that
clients cannot grow server memory without bound by creating objects.

```pycon
>>> s = LRUObjStore(max_size=2)
>>> s['a'], s['b'] = 1, 2
>>> _ = s['a']  # 'a' is now the most recently used
>>> s['c'] = 3
>>> sorted(s)
['a', 'c']
```

#### peek(k, default=None)

`self.get(k, default)`, without making `k` the most recently used.

### py2http.obj_dispatch.ObjOwner

`(request) -> owner`, a hashable that identifies an
*authenticated* client (e.g. a user id from a verified token). `None` and `""`
mean “not identified” and are refused. A client-chosen value (a session cookie the
client mints, an IP) lets one client create owners until others are evicted.

* **Type:**
  `obj_owner` hook

alias of `Callable`[[[`Any`](https://docs.python.org/3/library/typing.html#typing.Any)], [`Any`](https://docs.python.org/3/library/typing.html#typing.Any) | [`None`](https://docs.python.org/3/builtins/constants.html#None)]

### *class* py2http.obj_dispatch.OwnedObjStore(, quota=100, max_owners=1000)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

Objects kept per owner, with object and byte budgets. Thread-safe.

- `quota` objects per owner: an owner’s own least recently used object is evicted
  beyond it, never someone else’s;
- `max_owners` owners at once: the least recently active owner’s objects go;
- byte accounting: `record()` the size of an object; `owner_bytes()` and
  `total_bytes` sum what is currently stored.

```pycon
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
```

### py2http.obj_dispatch.current_request *: [ContextVar](https://docs.python.org/3/library/contextvars.html#contextvars.ContextVar)* *= <ContextVar name='py2http_current_request' default=None>*

The request being handled (set around every handler call), so per-request hooks such
as `obj_owner` can read it without the dispatched function taking it.

### py2http.obj_dispatch.public_attr(obj, attr_name)

The attribute policy `attr_names='*'` stands for: only public methods.

A name is dispatchable if it does not start with `_` and

- for a module: it is a function that the module defines (or lists in its
  `__all__`), never something it merely imports, nor plain data;
- otherwise: it is a plain Python function, `staticmethod`,
  `classmethod` or `property` defined in the object’s class (or a base
  class), and the instance does not shadow it.

This keeps private helpers, dunders (`__dict__`, `__init__`, …),
per-instance state (`__dict__` entries, `__slots__`, dataclass and
namedtuple fields) and callables merely assigned as class attributes
(`opener = open`) out of reach of HTTP clients.

Note that every public method is exposed, inherited ones included (e.g. a
pydantic model’s `model_dump`). For anything holding secrets, or a mapping
whose mutators should stay private (`MutableMapping` mixins such as
`clear` and `pop` are plain functions), list the names explicitly instead.

```pycon
>>> class A:
...     data = 0
...     opener = open
...     def f(self): ...
...     def _g(self): ...
...     def __init__(self): self.secret = 1
>>> [public_attr(A(), name)
...  for name in ('f', '_g', '__init__', '__dict__', 'secret', 'data', 'opener')]
[True, False, False, False, False, False, False]
```

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)

### py2http.obj_dispatch.unsafe_any_attr(obj, attr_name)

Dispatch ANY attribute of the object, including private ones and dunders.

This was the behaviour of `attr_names='*'` before `public_attr`: it lets a
client read `__dict__`, call `__init__` with arguments of its choosing, and so
on. Use `attr_names=unsafe_any_attr` only when every client is trusted.

* **Return type:**
  [`bool`](https://docs.python.org/3/builtins/functions.html#bool)
