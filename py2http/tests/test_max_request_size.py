"""``max_request_size`` raises bottle's in-memory body limit (i2mint/py2http#4)."""

import pytest

pytest.importorskip("bottle")
from bottle import BaseRequest

from py2http import mk_app


def echo(x: str):
    return x


def test_max_request_size_sets_bottle_limit():
    original = BaseRequest.MEMFILE_MAX
    try:
        mk_app([echo], framework="bottle", max_request_size=5_000_000)
        assert BaseRequest.MEMFILE_MAX == 5_000_000
    finally:
        BaseRequest.MEMFILE_MAX = original


def test_default_leaves_bottle_limit_alone():
    original = BaseRequest.MEMFILE_MAX
    mk_app([echo], framework="bottle")
    assert BaseRequest.MEMFILE_MAX == original
