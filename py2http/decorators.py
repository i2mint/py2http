from functools import wraps


def http_get(func):
    func.http_method = 'get'
    return func


def http_post(func):
    func.http_method = 'post'
    return func


def http_put(func):
    func.http_method = 'put'
    return func


def http_delete(func):
    func.http_method = 'delete'
    return func

# TODO: stub
def mk_input_mapper(input_map):
    def decorator(func):
        return func
    return decorator
