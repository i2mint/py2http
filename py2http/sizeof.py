"""Approximate the memory an object holds, without walking more of it than a budget.

``bounded_deep_sizeof`` is how py2http bounds the objects clients create or grow
through class and instance endpoints (``py2http.obj_dispatch``).
"""

import sys
from collections import deque
from functools import partial
from types import (
    BuiltinMethodType,
    FunctionType,
    MethodType,
    MethodWrapperType,
    ModuleType,
)
from typing import Optional

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
