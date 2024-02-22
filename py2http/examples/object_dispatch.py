"""This demonstrates how to use py2http to expose objects to REST APIs

Here we'll expose a simple dict as a REST API
Given the code actually only depends on the fact that the object is a MutableMapping,
(more precisely, that it has __iter__, __getitem__, and __setitem__ methods),
we could use the same code to expose any key-value view of any data source
(file system, blob storage, database, etc.) with the help of the `dol` library
and its ecosystem (mongodol, s3dol, etc.).

"""

from typing import MutableMapping


class BackendStore(MutableMapping):
    """MutableMapping wrapper that assumes that values are given as strings,
    but stored as bytes"""

    def __init__(self, store):
        self.store = store

    def __iter__(self):
        return list(self.store)

    def __getitem__(self, key: str) -> str:
        return self.store[key].decode()

    def __setitem__(self, key: str, value: str):
        self.store[key] = value.encode()

    def __len__(self) -> int:
        return len(self.store)

    def __delitem__(self, key: str):
        del self.store[key]


backend_store = BackendStore(
    {'some_key': b'some_value', 'some_other_key': b'some_other_value',}
)

handlers = [
    dict(
        endpoint=backend_store,
        name='backend_store',
        attr_names=['__iter__', '__getitem__', '__setitem__'],
    ),
]

from py2http import mk_app

app = mk_app(handlers, publish_openapi=True, publish_swagger=True)


def test_service(rooturl='http://localhost:8080'):
    import requests

    url = f'{rooturl}/backend_store'

    add_args = {
        '_attr_name': '__iter__',
    }
    assert requests.post(url, json=add_args).json() == ['some_key', 'some_other_key']

    add_args = {'_attr_name': '__getitem__', 'key': 'some_key'}
    assert requests.post(url, json=add_args).json() == 'some_value'


if __name__ == '__main__':
    app.run()


# old code (with errors)

# backend_store = {
#     'some_key': 'some_value',
#     'some_other_key': 'some_other_value',
# }


# handlers = [
#     dict(
#         endpoint=backend_store,
#         name='backend_store',
#         attr_names=['__iter__', '__getitem__', '__setitem__'],
#     )
# ]

# from py2http import mk_app

# app = mk_app(handlers, publish_openapi=True, publish_swagger=True)


# if __name__ == '__main__':
#     app.run()
