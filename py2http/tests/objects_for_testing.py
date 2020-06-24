"""
A module containing a bunch of objects for testing.

See also: https://github.com/i2mint/py2mint/blob/master/py2mint/tests/objects_for_testing.py
"""


def add(a, b: float = 0.0) -> float:
    """Adds numbers"""
    return a + b


def mult(x: float, y=1):
    return x * y


# This one has every of the 4 combinations of (default y/n, annotated y/n)
def formula1(w, x: float, y=1, z: int = 1):
    return ((w + x) * y) ** z
