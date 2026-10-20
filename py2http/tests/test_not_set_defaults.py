"""``i2``'s ``NotSet`` sentinel in a signature means "required / no default".

See i2mint/i2#48: once ``i2.FuncFactory`` shows ``NotSet`` defaults, the OpenAPI spec
py2http builds must stay JSON-serializable and keep those params required.
These tests use ``i2.deco.NotSet`` directly, so they pass with any i2 version.
"""

import json
from inspect import Parameter

import pytest
from i2 import Sig
from i2.deco import NotSet

from py2http.decorators import ParamsSpecifier
from py2http.schema_tools import mk_input_schema_from_func
from py2http.service import mk_routes_and_openapi_specs


def foo(a: int, b: str, c=None, *, d: float = 1.5):
    return a, b, c, d


# ``foo`` with ``NotSet`` defaults, as a re-landed i2#88 ``FuncFactory`` would show.
# Defined separately (rather than with ``Sig(foo).ch_defaults(...)(foo)``), since
# ``Sig.__call__`` sets ``__signature__`` on ``foo`` itself, in place. No docstring,
# so that its OpenAPI spec can be compared with foo's.
def foo_with_not_set(a: int = NotSet, b: str = NotSet, c=None, *, d: float = 1.5):
    return a, b, c, d


foo_with_not_set.__name__ = foo.__name__  # same route and spec as foo


def test_fixture_really_has_not_set_defaults():
    assert Sig(foo_with_not_set).parameters["a"].default is NotSet


def test_input_schema_is_the_same_as_without_not_set():
    assert mk_input_schema_from_func(foo_with_not_set) == mk_input_schema_from_func(foo)
    assert mk_input_schema_from_func(foo_with_not_set)["required"] == ["a", "b"]


def test_openapi_spec_is_json_serializable_and_marks_required():
    _, spec = mk_routes_and_openapi_specs([foo_with_not_set])
    serialized = json.dumps(spec)  # used to raise: Sentinel is not JSON serializable
    assert "NotSet" not in serialized
    _, plain_spec = mk_routes_and_openapi_specs([foo])
    assert spec == plain_spec


def test_params_specifier_does_not_take_not_set_as_default():
    specifier = ParamsSpecifier.from_func(foo_with_not_set, _dflt_default="dflt")
    assert specifier._name_and_dflts == {"a": "dflt", "b": "dflt", "c": None, "d": 1.5}


def test_openapi_spec_of_a_func_factory_showing_not_set_defaults():
    """What a re-landed i2#88 does: a ``FuncFactory`` whose signature shows ``NotSet``."""
    from i2 import FuncFactory

    def mk_factory():
        factory = FuncFactory(foo)
        factory.__name__ = "foo_factory"  # FuncFactory instances have no __name__
        return factory

    plain, with_not_set = mk_factory(), mk_factory()
    sig = Sig(with_not_set)
    with_not_set.__signature__ = sig.ch_defaults(
        **{name: NotSet for name in sig.required_names}
    )
    assert Sig(with_not_set).parameters["a"].default is NotSet

    _, spec = mk_routes_and_openapi_specs([with_not_set])
    assert "NotSet" not in json.dumps(spec)
    assert spec == mk_routes_and_openapi_specs([plain])[1]


try:
    from i2 import is_placeholder_default as _  # noqa: F401

    _HAS_PLACEHOLDERS = True
except ImportError:
    _HAS_PLACEHOLDERS = False


@pytest.mark.skipif(not _HAS_PLACEHOLDERS, reason="i2 without DefaultPlaceholder")
def test_methodize_default_from_placeholder_is_no_default():
    """i2mint/py2http#49: a ``methodize(..., default_from=...)`` default is a marker,
    not a value: the schema keeps that param required, with no default.
    """
    from dataclasses import dataclass

    from i2.wrapper import methodize

    def baz(x, y: int, z: int, *, d: float = 1.5):
        return x + y * z + d

    @dataclass
    class K:
        x: int
        zoo: int = 2
        bar = methodize(baz, bind="x", default_from=[("z", "zoo")])

    method = K(1).bar
    assert Sig(method).parameters["z"].default is not Parameter.empty  # marker is there

    schema = mk_input_schema_from_func(method)
    assert schema["required"] == ["y", "z"]
    assert "default" not in schema["properties"]["z"]

    specifier = ParamsSpecifier.from_func(method, _dflt_default="dflt")
    assert specifier._name_and_dflts == {"y": "dflt", "z": "dflt", "d": 1.5}
