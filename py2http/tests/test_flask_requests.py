"""Under ``framework='flask'`` the non-JSON input mappers read Flask's request, the
``send_*_resp`` mappers answer their content type, and a bad body is a 400."""

import json
import pickle

import pytest

from py2http import mk_app
from py2http.constants import (
    BINARY_CONTENT_TYPE,
    FORM_CONTENT_TYPE,
    JSON_CONTENT_TYPE,
    RAW_CONTENT_TYPE,
)
from py2http.decorators import (
    handle_binary_req,
    handle_form_req,
    handle_raw_req,
    send_binary_resp,
    send_json_resp,
    send_raw_resp,
    unsafe_pickle_loads,
)

pytest.importorskip("flask")


def _client(func, **configs):
    return mk_app([func], framework="flask", **configs).test_client()


def add(x: int, y: int = 1):
    return x + y


def upload(name: str, data: bytes):
    return f"{name}:{len(data)}"


def test_raw_req():
    r = _client(add, input_mapper=handle_raw_req(lambda x, y=1: dict(x=x, y=y))).post(
        "/add", data=json.dumps({"x": 1}), content_type=RAW_CONTENT_TYPE
    )
    assert (r.status_code, r.get_json()) == (200, 2)


def test_binary_req():
    mapper = handle_binary_req(lambda x, y=1: dict(x=x, y=y), loads=unsafe_pickle_loads)
    r = _client(add, input_mapper=mapper).post(
        "/add", data=pickle.dumps({"x": 3, "y": 4}), content_type=BINARY_CONTENT_TYPE
    )
    assert (r.status_code, r.get_json()) == (200, 7)


def test_form_req():
    import io

    mapper = handle_form_req(lambda name, data: dict(name=name, data=data))
    r = _client(upload, input_mapper=mapper).post(
        "/upload",
        data={
            "__fields": (io.BytesIO(b'{"name": "n"}'), "__fields"),
            "data": (io.BytesIO(b"abc"), "data"),
        },
        content_type="multipart/form-data",
    )
    assert (r.status_code, r.get_json()) == (200, "n:3")


@pytest.mark.parametrize(
    "decorator, content_type, body, expected",
    [
        (send_raw_resp, RAW_CONTENT_TYPE, "hi", b"hi"),
        (send_binary_resp, BINARY_CONTENT_TYPE, "hi", pickle.dumps("hi")),
        (send_json_resp, JSON_CONTENT_TYPE, {"a": 1}, b'{"a": 1}'),
    ],
)
def test_send_resp_content_type(decorator, content_type, body, expected):
    mapper = decorator(lambda output, **_: body)
    r = _client(add, output_mapper=mapper).post("/add", json={"x": 1})
    assert r.status_code == 200
    assert r.content_type.split(";")[0] == content_type
    assert r.data == expected


@pytest.mark.parametrize(
    "body, content_type",
    [
        (b"", JSON_CONTENT_TYPE),
        (b"   ", JSON_CONTENT_TYPE),
        (b"{not json", JSON_CONTENT_TYPE),
        (b"[1, 2]", JSON_CONTENT_TYPE),
        (b"\xff\xfe", JSON_CONTENT_TYPE),
        (b'{"x": 1}', "text/plain"),
        (b'{"x": 1}', None),
    ],
)
def test_bad_bodies_are_400(body, content_type):
    kwargs = {"content_type": content_type} if content_type else {}
    r = _client(add).post("/add", data=body, **kwargs)
    assert r.status_code == 400
    assert "Traceback" not in r.get_data(as_text=True)
    assert r.get_json()["error"]


def test_bottle_bad_body_is_400():
    from wsgiref.util import setup_testing_defaults
    import io

    app = mk_app([add])
    environ = {}
    setup_testing_defaults(environ)
    environ.update(
        REQUEST_METHOD="POST",
        PATH_INFO="/add",
        CONTENT_TYPE=JSON_CONTENT_TYPE,
        CONTENT_LENGTH="0",
    )
    environ["wsgi.input"] = io.BytesIO(b"")
    out = {}
    app(environ, lambda status, headers, *a: out.setdefault("status", status))
    assert out["status"].startswith("400")


@pytest.mark.parametrize(
    "body, content_type",
    [
        (b"\xef\xbb\xbf" + b'{"x": 2}', JSON_CONTENT_TYPE),  # UTF-8 with a BOM
        ('{"x": 2}'.encode("utf-16"), JSON_CONTENT_TYPE),
        (b'{"x": 2}', "Application/JSON"),  # media types are case-insensitive
    ],
)
def test_json_encodings_and_content_type_case(body, content_type):
    r = _client(add).post("/add", data=body, content_type=content_type)
    assert (r.status_code, r.get_json()) == (200, 3)


# --- i2mint/py2http#44 -----------------------------------------------------------------


def _mapper_with_content_type(fn, content_type=RAW_CONTENT_TYPE, *, is_async=False):
    if is_async:

        async def mapper(output, **inputs):
            return fn(output)

    else:

        def mapper(output, **inputs):
            return fn(output)

    mapper.content_type = content_type
    return mapper


@pytest.mark.parametrize("is_async", [False, True])
@pytest.mark.parametrize(
    "returned, status, expected",
    [("hi", 200, b"hi"), (("hi", 201), 201, b"hi"), ((b"hi", 202, {"X-A": "1"}), 202, b"hi")],
)
def test_output_mapper_content_type_survives_async_and_status_tuples(
    is_async, returned, status, expected
):
    mapper = _mapper_with_content_type(lambda out: returned, is_async=is_async)
    r = _client(add, output_mapper=mapper).post("/add", json={"x": 1})
    assert (r.status_code, r.data) == (status, expected)
    assert r.content_type.split(";")[0] == RAW_CONTENT_TYPE


def test_a_tuple_with_its_own_content_type_header_keeps_it():
    mapper = _mapper_with_content_type(lambda out: ("hi", 200, {"Content-Type": "text/csv"}))
    r = _client(add, output_mapper=mapper).post("/add", json={"x": 1})
    assert r.content_type.split(";")[0] == "text/csv"


def sizes(data: bytes):
    return [len(d) for d in data] if isinstance(data, list) else len(data)


def _post_files(*files):
    import io

    mapper = handle_form_req(lambda data: dict(data=data))
    data = {"__fields": (io.BytesIO(b"{}"), "__fields")}
    data["data"] = [(io.BytesIO(b), "data") for b in files] if len(files) > 1 else (io.BytesIO(files[0]), "data")
    return _client(sizes, input_mapper=mapper).post("/sizes", data=data, content_type="multipart/form-data")


def test_several_files_under_one_form_field_are_all_kept():
    assert _post_files(b"a", b"bb", b"ccc").get_json() == [1, 2, 3]
    assert _post_files(b"abcd").get_json() == 4  # one file stays a bare bytes


def test_max_request_size_sets_flask_max_content_length():
    app = mk_app([add], framework="flask", max_request_size=1000)
    assert app.config["MAX_CONTENT_LENGTH"] == 1000
    r = app.test_client().post("/add", data=b"x" * 2000, content_type=JSON_CONTENT_TYPE)
    assert r.status_code == 413
    assert app.test_client().post("/add", json={"x": 1}).status_code == 200
    assert mk_app([add], framework="flask").config["MAX_CONTENT_LENGTH"] is None


def test_a_tuple_with_werkzeug_headers_keeps_them():
    from werkzeug.datastructures import Headers

    mapper = _mapper_with_content_type(lambda out: ("hi", 201, Headers([("X-A", "1")])))
    r = _client(add, output_mapper=mapper).post("/add", json={"x": 1})
    assert (r.status_code, r.headers["X-A"]) == (201, "1")


def test_a_werkzeug_4xx_keeps_the_headers_it_carries():
    from werkzeug.exceptions import MethodNotAllowed
    from py2http.default_configs import flask_error_handler

    _, status, headers = flask_error_handler(MethodNotAllowed(["POST"]))
    assert status == 405 and headers["Allow"] == "POST"
