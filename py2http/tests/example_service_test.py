import pytest  # TODO: Figure out how to make it a pytest...
import requests

dflt_port = '3030'


def example_test(port=dflt_port):
    add_result = requests.post(f'http://localhost:{port}/add', json={'a': 10, 'b': 5})
    assert str(add_result.json()) == '15'

    multiply_result = requests.post(f'http://localhost:{port}/multiply', json={'multiplier': 6})
    assert str(multiply_result.json()) == '30'

    no_args_result = requests.post(f'http://localhost:{port}/no_args', json={})
    assert str(no_args_result.json()) == 'no args'


if __name__ == '__main__':
    from .utils_for_testing import run_server
    from .example_service import run_example_service

    with run_server(run_example_service, wait_before_entering=0.5):
        example_test()
