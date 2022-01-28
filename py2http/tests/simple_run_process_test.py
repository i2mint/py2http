from py2http.tests.test_p2h2p import get_client_funcs, run_app
from py2http.util import run_process
from time import sleep

import inspect

ddir = lambda o: [x for x in dir(o) if not x.startswith('_')]


def print_source(*funcs):
    for func in funcs:
        print(inspect.getsource(func))


class Struct:
    def __init__(self, **kwargs):
        for attr, val in kwargs.items():
            setattr(self, attr, val)


from py2http.tests.objects_for_testing import add, mult, formula1
import requests

funcs = [add, mult, formula1]


def json_response(r):
    return r.json()


def output_mapper(r, ignored):
    # print(r)  # Whaaaa?! I get an int here, not a response object!
    return r
    # return r.json()


# getting functions that call the http service endpoints and making a struct to hold these:

p2h_configs = dict(output_mapper=output_mapper)
h2p_configs = dict(output_trans=json_response)  # applied to all funcs
c = Struct(
    **{
        x.__name__: x
        for x in get_client_funcs(
            funcs, p2h_configs=p2h_configs, h2p_configs=h2p_configs
        )
    }
)

assert set(ddir(c)) == {'add', 'mult', 'formula1'}


def my_print(*args):
    sleep(1)
    print(*args)


if __name__ == '__main__':
    # print_source(*funcs)

    def test_run_app():
        def is_server_up():
            try:
                return requests.get(url='http://localhost:3030/ping').status_code == 200
            except requests.exceptions.ConnectionError:
                return False

        process = run_process(
            func=run_app,
            func_args=(funcs,),
            func_kwargs=dict({}, output_mapper=output_mapper),
            is_ready=is_server_up,
            verbose=True,
        )
        with process:
            add_r = c.add(0.14156, 3)
            mult_r = c.mult(14, y=3)
            formula1_r = c.formula1(2, 3, 4, 5)

        # print(add_r)
        # With json_response:
        assert add_r == add(0.14156, 3)
        assert mult_r == mult(14, y=3)
        assert formula1_r == formula1(2, 3, 4, 5)

        # # With raw response:
        # assert float(add_r.content) == add(0.14156, 3)
        # assert float(mult_r.content) == mult(14, y=3)
        # assert float(formula1_r.content) == formula1(2, 3, 4, 5)

    def test_my_print():
        process = run_process(
            func=my_print, func_args=('hello world',), force_kill=False, verbose=True,
        )

        with process:
            # process.join()
            print('test')

    # test_my_print()
    test_run_app()
