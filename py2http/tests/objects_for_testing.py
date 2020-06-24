"""
A module containing a bunch of objects for testing.

See also: https://github.com/i2mint/py2mint/blob/master/py2mint/tests/objects_for_testing.py
"""


###############################################################################
# Empty callables, meant to give an example of different kinds of callables ###
# Note that x can be applied to a number, string, or list #####################
def f(x):
    """Note that x can be applied to a number, string, or list"""
    return x * 2


class C:
    @classmethod
    def c(cls, x):
        return f(x)

    @staticmethod
    def s(x):
        return f(x)

    # instance method
    def i(self, x):
        return f(x)

    # making an instance itself callable
    def __call__(self, x):
        return f(x)


###############################################################################


def add(a, b: float = 0.0) -> float:
    """Adds numbers"""
    return a + b


def mult(x: float, y=1):
    return x * y


# This one has every of the 4 combinations of (default y/n, annotated y/n)
def formula1(w, x: float, y=1, z: int = 1):
    return ((w + x) * y) ** z
