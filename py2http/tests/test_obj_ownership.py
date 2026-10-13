"""Class-endpoint objects belong to their creator and are bounded in size (#22)."""

import io
import json
from wsgiref.util import setup_testing_defaults

import pytest
from i2.errors import AuthorizationError, InputError

from py2http import mk_app
from py2http.service import (
    OwnedObjStore,
    _get_func_to_dispatch_handler,
    bounded_deep_sizeof,
    current_request,
    shared_objects,
)


class Bag:
    def __init__(self):
        self.items = []

    def add(self, item=None):
        self.items.append(item)
        return len(self.items)


def _owned(**extras):
    extras.setdefault("obj_owner", lambda req: req)  # the "request" is the owner here
    return _get_func_to_dispatch_handler(
        dict(endpoint=Bag, name="bag", attr_names="*", **extras)
    )


def _as(owner, func, **kwargs):
    token = current_request.set(owner)
    try:
        return func(**kwargs)
    finally:
        current_request.reset(token)


def test_class_endpoint_without_owner_is_refused_at_build():
    with pytest.raises(ValueError, match="obj_owner"):
        _get_func_to_dispatch_handler(dict(endpoint=Bag, name="bag", attr_names="*"))


def test_other_owners_objects_are_not_found():
    func = _owned()
    ann_bag = _as("ann", func)
    assert _as("ann", func, _obj_id=ann_bag, _attr_name="add", item=1) == 1
    with pytest.raises(InputError, match="No object found"):
        _as("bob", func, _obj_id=ann_bag, _attr_name="add", item=2)


def test_unidentified_request_is_refused():
    func = _owned()
    with pytest.raises(AuthorizationError):
        _as(None, func)


def test_quota_evicts_only_the_owners_own_objects():
    func = _owned(obj_quota=2)
    bob_bag = _as("bob", func)
    ann_bags = [_as("ann", func) for _ in range(3)]
    with pytest.raises(InputError, match="No object found"):
        _as("ann", func, _obj_id=ann_bags[0], _attr_name="add")
    assert _as("ann", func, _obj_id=ann_bags[2], _attr_name="add") == 1
    assert _as("bob", func, _obj_id=bob_bag, _attr_name="add") == 1


def test_obj_store_is_for_shared_mode_only():
    with pytest.raises(ValueError, match="shared_objects"):
        _owned(obj_store={})
    with pytest.raises(TypeError, match="callable"):
        _owned(obj_owner="ann")


def test_shared_objects_opt_in_restores_capability_ids():
    func = _owned(obj_owner=shared_objects)
    bag = _as("ann", func)
    assert _as("bob", func, _obj_id=bag, _attr_name="add") == 1


def test_object_growing_past_the_size_limit_is_dropped():
    func = _owned(max_obj_size=5_000)
    bag = _as("ann", func)
    _as("ann", func, _obj_id=bag, _attr_name="add", item="x")
    with pytest.raises(InputError, match="size limit"):
        _as("ann", func, _obj_id=bag, _attr_name="add", item="y" * 10_000)
    with pytest.raises(InputError, match="No object found"):
        _as("ann", func, _obj_id=bag, _attr_name="add")


def test_size_check_can_be_disabled_or_replaced():
    func = _owned(max_obj_size=None)
    bag = _as("ann", func)
    _as("ann", func, _obj_id=bag, _attr_name="add", item="y" * 100_000)
    func = _owned(max_obj_size=1, obj_sizeof=lambda obj, limit: 0)
    _as("ann", func, _obj_id=_as("ann", func), _attr_name="add", item="y")


def test_bounded_deep_sizeof_sees_slots_and_stops_early():
    class Slotted:
        __slots__ = ("payload",)

        def __init__(self, payload):
            self.payload = payload

    assert bounded_deep_sizeof(Slotted("y" * 10_000)) > 10_000
    assert bounded_deep_sizeof(Bag()) < bounded_deep_sizeof(_full_bag())


def _full_bag():
    b = Bag()
    b.items.extend(range(1000))
    return b


def test_owned_store_rejects_bad_bounds():
    with pytest.raises(ValueError):
        OwnedObjStore(quota=0)
    with pytest.raises(ValueError):
        OwnedObjStore(max_owners=0)


# ------------------------------------------------- end to end, through a real request


def _post(app, path, payload, user):
    body = json.dumps(payload).encode()
    environ = {}
    setup_testing_defaults(environ)
    environ.update(
        REQUEST_METHOD="POST",
        PATH_INFO=path,
        CONTENT_TYPE="application/json",
        CONTENT_LENGTH=str(len(body)),
        HTTP_X_USER=user,
    )
    environ["wsgi.input"] = io.BytesIO(body)
    statuses = []
    out = b"".join(app(environ, lambda status, headers, *a: statuses.append(status)))
    return statuses[0], json.loads(out)


def test_owner_hook_reads_the_real_request():
    app = mk_app(
        [
            dict(
                endpoint=Bag,
                name="bag",
                attr_names="*",
                obj_owner=lambda req: req.headers.get("X-User") or None,
            )
        ]
    )
    status, bag = _post(app, "/bag", {}, "ann")
    assert status.startswith("200")
    status, n = _post(app, "/bag", {"_obj_id": bag, "_attr_name": "add"}, "ann")
    assert status.startswith("200") and n == 1
    status, _ = _post(app, "/bag", {"_obj_id": bag, "_attr_name": "add"}, "bob")
    assert not status.startswith("2")
    status, _ = _post(app, "/bag", {}, "")
    assert not status.startswith("2")
