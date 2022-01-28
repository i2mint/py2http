from py2http import run_app
from py2http.config import FLASK
from py2http.default_configs import flask_output_mapper


def add(a, b: int = 0):
    return a + b


def no_args():
    return 'no args'


class MultiplierClass:
    def __init__(self, multiplicand):
        self.multiplicand = multiplicand

    def multiply(self, multiplier):
        return self.multiplicand * multiplier


multiplier_instance = MultiplierClass(5)


example_functions = [add, no_args, multiplier_instance.multiply]


if __name__ == '__main__':
    run_app(
        example_functions,
        framework=FLASK,
        http_method='GET',
        output_mapper=flask_output_mapper,
    )
