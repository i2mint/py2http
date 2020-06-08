from py2http import run_http_service


class ExampleController:
    def add(self, a, b):
        return a + b

    def no_args(self):
        return 'no args'

    def __call__(self):
        return 'base route'


controller = ExampleController()


if __name__ == '__main__':
    run_http_service(controller)
