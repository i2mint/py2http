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
