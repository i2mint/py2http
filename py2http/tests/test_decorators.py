import pytest

from py2http.decorators import Decora, ParamsSpecifier, signature


# First let's see what happens when you use D that does nothing
def test_transparent_decora():
    def assert_f_and_g_are_the_same(f, g):
        assert g(42) == f(42)  # computation remains the same
        assert signature(g) == signature(f)  # signature remains the same

    def _test_sameness(decora_cls):
        """This is to test a decorator that is meant to do nothing to the actual decorated function
        (but wrap it in a class)"""

        f = lambda x, y=0: (x + y)
        g = decora_cls(f)  # decorate this way
        assert_f_and_g_are_the_same(f, g)

        decorator = decora_cls()  # make a decorator, and
        g = decorator(f)  # ... decorate that way
        assert_f_and_g_are_the_same(f, g)

        # which is equivalent to
        @decora_cls
        def g(x, y=0):
            return x + y

        assert_f_and_g_are_the_same(f, g)

        return True

    class Deco(Decora):
        class whatevs(ParamsSpecifier):
            b = 3
            z: float
            c: int = 2

    assert _test_sameness(Deco)

    assert str(signature(Deco)) == '(func=None, *, z: float = None, b=3, c: int = 2)'

    # Here's another way to inject your decorator factory's params
    class whatevs(ParamsSpecifier):
        b = 3
        z: float
        c: int = 2

    class Deco(Decora):
        my_params = whatevs()

    assert _test_sameness(Deco)

    assert str(signature(Deco)) == '(func=None, *, z: float = None, b=3, c: int = 2)'


def test_simple_decora():
    class whatevs(ParamsSpecifier):
        minus = 3
        times: float
        repeat: int = 2

    class Deco(Decora):
        my_params = whatevs()

        def __call__(self, *args, **kwargs):
            func_result = super().__call__(*args, **kwargs)
            return (
                func_result[0],
                [func_result[1] * self.times - self.minus] * self.repeat,
            )

    def f(w: float, x: int = 0, greet='hi'):
        return greet, w + x

    g = Deco(times=3)(f)
    assert g(0) == ('hi', [-3] * 2)
    assert g(10) == ('hi', [27] * 2)
    assert g(10, x=1, greet='hello') == ('hello', [30, 30])

    g = Deco(f, times=1, minus=2, repeat=3)
    assert g(0) == ('hi', [-2, -2, -2])
    g = Deco(times=0, minus=3, repeat=1)(f)
    assert g(10) == ('hi', [-3])
    g = Deco(times=2, minus=0, repeat=1)(f)
    assert g(10) == ('hi', [20])
