"""This demonstrates how to use py2http to expose objects to REST APIs"""

# Here we'll expose a simple dict as a REST API
# Given the code actually only depends on the fact that the object is a MutableMapping,
# (more precisely, that it has __iter__, __getitem__, and __setitem__ methods),
# we could use the same code to expose any key-value view of any data source
# (file system, blob storage, database, etc.) with the help of the `dol` library
# and its ecosystem (mongodol, s3dol, etc.).
backend_store = {
    'some_key': b'some_value',
    'some_other_key': b'some_other_value',
}

handlers = [
    dict(
        endpoint=backend_store,
        name='backend_store',
        attr_names=['__iter__', '__getitem__', '__setitem__'],
    ),
]

from py2http import mk_app

app = mk_app(handlers, publish_openapi=True, publish_swagger=True)


if __name__ == '__main__':
    app.run()
