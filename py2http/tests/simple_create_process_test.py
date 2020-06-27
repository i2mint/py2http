from py2http.tests.test_p2h2p import get_client_funcs, run_http_service
from py2http.util import CreateProcess

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
c = Struct(**{x.__name__: x for x in get_client_funcs(
    funcs, p2h_configs=p2h_configs, h2p_configs=h2p_configs)})

assert set(ddir(c)) == {'add', 'mult', 'formula1'}

if __name__ == '__main__':
    print_source(*funcs)


    def test():
        process = CreateProcess(run_http_service,
                                wait_before_entering=2, verbose=True, args=(funcs,),
                                output_mapper=output_mapper)
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


    test()
