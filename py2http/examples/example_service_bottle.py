from py2http import run_app
from py2http.config import BOTTLE
from py2http.decorators import binary_output
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


@binary_output
def binary_string():
    return b'Here is a binary response'


multiplier_instance = MultiplierClass(5)


example_functions = [add, no_args, multiplier_instance.multiply, binary_string]


if __name__ == '__main__':
    run_app(
        example_functions,
        framework=BOTTLE,
        http_method='POST',
        input_mapper=input_mapper,
        output_mapper=bottle_output_mapper,
        publish_swagger=True,
    )
