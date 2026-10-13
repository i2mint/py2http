"""Object/attribute dispatch (``attr_names``) only exposes what was meant to be exposed."""

import pytest
from i2.errors import InputError

from py2http.service import (
    LRUObjStore,
    _get_func_to_dispatch_handler,
    public_attr,
    unsafe_any_attr,
)


class Counter:
    def __init__(self, start: int = 0):
        self.count = start
        self._secret = "s3cr3t"

    def incr(self, by: int = 1):
        self.count += by
        return self.count

    def _reset(self):
        self.count = 0


def _dispatcher(endpoint, attr_names, **handler_extras):
    return _get_func_to_dispatch_handler(
        dict(endpoint=endpoint, name="ep", attr_names=attr_names, **handler_extras)
    )


@pytest.mark.parametrize(
    "attr_name", ["_reset", "_secret", "__dict__", "__init__", "__class__", "count"]
)
def test_star_refuses_private_dunder_and_instance_attrs(attr_name):
    obj = Counter(5)
    func = _dispatcher(obj, "*")
    with pytest.raises(InputError):
        func(_attr_name=attr_name)
    assert obj.count == 5


def test_star_allows_public_methods():
    func = _dispatcher(Counter(5), "*")
    assert func(_attr_name="incr", by=2) == 7


def test_star_on_class_endpoint():
    func = _dispatcher(Counter, "*")
    obj_id = func(start=3)
    assert func(_obj_id=obj_id, _attr_name="incr") == 4
    for attr_name in ("__init__", "__dict__", "_secret", "mro"):
        with pytest.raises(InputError):
            func(_obj_id=obj_id, _attr_name=attr_name)


def test_explicit_list_unaffected():
    """An explicit allow-list may name dunders on purpose (see examples/object_dispatch)."""
    class Store(dict):
        def __getitem__(self, key):
            return super().__getitem__(key)

    d = Store(a=1)
    func = _dispatcher(d, ["__getitem__", "__len__"])
    assert func(_attr_name="__getitem__", key="a") == 1
    assert func(_attr_name="__len__") == 1
    with pytest.raises(InputError):
        func(_attr_name="clear")
    with pytest.raises(InputError):
        func(_attr_name="__dict__")
    assert d == {"a": 1}


def test_unsafe_any_attr_opt_in_restores_old_behaviour():
    obj = Counter(5)
    func = _dispatcher(obj, unsafe_any_attr)
    func(_attr_name="_reset")
    assert obj.count == 0


def test_custom_predicate():
    func = _dispatcher(Counter(1), lambda obj, name: name == "incr")
    assert func(_attr_name="incr") == 2


def test_public_attr_on_module():
    import json

    assert public_attr(json, "dumps")
    assert not public_attr(json, "_default_encoder")
    assert not public_attr(json, "__loader__")


def test_obj_store_is_bounded():
    store = LRUObjStore(max_size=2)
    func = _dispatcher(Counter, "*", obj_store=store)
    ids = [func(start=i) for i in range(3)]
    assert len(store) == 2
    with pytest.raises(InputError, match="No object found"):
        func(_obj_id=ids[0], _attr_name="incr")
    assert func(_obj_id=ids[2], _attr_name="incr") == 3


def test_obj_store_default_is_bounded_lru():
    func = _dispatcher(Counter, "*")
    obj_id = func()
    assert func(_obj_id=obj_id, _attr_name="incr") == 1


def test_falsy_object_is_still_found():
    func = _dispatcher(list, ["append", "__len__"])
    obj_id = func()  # an empty list is falsy
    assert func(_obj_id=obj_id, _attr_name="__len__") == 0


def test_lru_obj_store_rejects_bad_size():
    with pytest.raises(ValueError):
        LRUObjStore(max_size=0)


# --- shapes found by the adversarial review: instance state must stay private ---

from dataclasses import dataclass
from types import ModuleType
from typing import NamedTuple


class Slotted:
    __slots__ = ("token",)

    def __init__(self):
        self.token = "TOK"

    def ping(self):
        return "pong"


@dataclass
class DC:
    token: str = "default"

    def ping(self):
        return "pong"


class NT(NamedTuple):
    token: str

    def ping(self):
        return "pong"


class Odd:
    count = 0
    opener = open
    Nested = dict

    def __init__(self):
        self.count = 42
        self.incr = lambda: "shadowed"

    def incr(self):
        return "real"

    @staticmethod
    def s():
        return "static"

    @classmethod
    def c(cls):
        return "class"

    @property
    def p(self):
        return "prop"


@pytest.mark.parametrize(
    "obj", [Slotted(), DC(token="TOK"), NT(token="TOK")], ids=["slots", "dc", "nt"]
)
def test_star_refuses_fields(obj):
    func = _dispatcher(obj, "*")
    with pytest.raises(InputError):
        func(_attr_name="token")
    assert func(_attr_name="ping") == "pong"


@pytest.mark.parametrize("attr_name", ["count", "opener", "Nested", "incr"])
def test_star_refuses_data_shadowed_and_assigned_callables(attr_name):
    func = _dispatcher(Odd(), "*")
    with pytest.raises(InputError):
        func(_attr_name=attr_name)


def test_star_allows_static_class_methods_and_properties():
    func = _dispatcher(Odd(), "*")
    assert [func(_attr_name=n) for n in ("s", "c", "p")] == ["static", "class", "prop"]


def test_star_refuses_builtin_mapping_mutators():
    class Store(dict):
        def keys_list(self):
            return list(self)

    d = Store(a=1)
    func = _dispatcher(d, "*")
    with pytest.raises(InputError):
        func(_attr_name="clear")
    assert func(_attr_name="keys_list") == ["a"] and d == {"a": 1}


def _mk_module(name, *, all_=None):
    mod = ModuleType(name)
    exec(
        "from os import listdir\nfrom json import dumps\nimport os\nAPI_KEY = 'k-123'\n"
        "def hello():\n    return 'hi'\n",
        vars(mod),
    )
    if all_ is not None:
        mod.__all__ = all_
    return mod


@pytest.mark.parametrize("attr_name", ["listdir", "dumps", "os", "API_KEY"])
def test_star_on_module_refuses_imports_and_data(attr_name):
    func = _dispatcher(_mk_module("some_service"), "*")
    with pytest.raises(InputError):
        func(_attr_name=attr_name)
    assert func(_attr_name="hello") == "hi"


def test_star_on_module_honours_all():
    mod = _mk_module("some_service", all_=["dumps", "listdir"])
    assert public_attr(mod, "dumps")  # a re-export listed in __all__
    assert not public_attr(mod, "listdir")  # listed, but not a Python function
    assert not public_attr(mod, "hello")  # not listed


@pytest.mark.parametrize("bad", [["x"], {"a": 1}, 3, None])
def test_non_str_names_and_ids_are_input_errors(bad):
    func = _dispatcher({"x": 1}, ["x", "__len__"])
    if bad is not None:
        with pytest.raises(InputError):
            func(_attr_name=bad)
    cls_func = _dispatcher(Counter, "*")
    with pytest.raises(InputError):
        cls_func(_obj_id=bad if bad is not None else [], _attr_name="incr")


def test_method_params_named_like_dispatch_internals():
    class A:
        def f(self, obj, attr_name, is_dispatchable):
            return [obj, attr_name, is_dispatchable]

    func = _dispatcher(A(), "*")
    assert func(_attr_name="f", obj=1, attr_name=2, is_dispatchable=3) == [1, 2, 3]


def test_star_exposes_mutable_mapping_mixins_as_documented():
    """Inherited public Python methods ARE dispatched: use an explicit list for stores."""
    from collections.abc import MutableMapping

    class MM(MutableMapping):
        def __init__(self):
            self._d = {"a": 1}

        def __getitem__(self, k):
            return self._d[k]

        def __setitem__(self, k, v):
            self._d[k] = v

        def __delitem__(self, k):
            del self._d[k]

        def __iter__(self):
            return iter(self._d)

        def __len__(self):
            return len(self._d)

    assert public_attr(MM(), "clear")
