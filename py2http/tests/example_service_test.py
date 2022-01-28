# import pytest  # TODO: Figure out how to make it a pytest...
import requests

dflt_port = '3030'
dflt_root_url = 'http://localhost'
dflt_base_url = dflt_root_url + ':' + dflt_port


def example_test(base_url=dflt_base_url):
    print('starting test')
    add_result = requests.post(f'{base_url}/add', json={'a': 10, 'b': 5})
    assert str(add_result.json()) == '15'

    multiply_result = requests.post(f'{base_url}/multiply', json={'multiplier': 6})
    assert str(multiply_result.json()) == '30'

    no_args_result = requests.post(f'{base_url}/no_args', json={})
    assert str(no_args_result.json()) == 'no args'
    print('ending test')


if __name__ == '__main__':
    from py2http.tests.utils_for_testing import run_server
    from py2http.examples.example_service import (
        example_functions,
        run_app,
    )

    def run_example_service():
        return run_app(example_functions)

    with run_server(run_example_service, wait_before_entering=0.5):
        example_test()
