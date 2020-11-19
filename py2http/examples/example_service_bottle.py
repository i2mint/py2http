from py2http import run_http_service
from py2http.config import BOTTLE
from py2http.default_configs import bottle_output_mapper


def add(a, b: int = 0):
    return a + b


def no_args():
    return 'no args'


class MultiplierClass:
    def __init__(self, multiplicand):
        self.multiplicand = multiplicand

    def multiply(self, multiplier):
        return self.multiplicand * multiplier


def input_mapper(req, schema):
    print(f'input: {str(req.json)}')
    return req.json


multiplier_instance = MultiplierClass(5)


example_functions = [add, no_args, multiplier_instance.multiply]


if __name__ == '__main__':
    run_http_service(
        example_functions,
        framework=BOTTLE,
        http_method='POST',
        input_mapper=input_mapper,
        output_mapper=bottle_output_mapper,
    )
