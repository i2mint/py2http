"""Tests for util.py"""

from inspect import signature
from py2http.util import gather_arguments_into_single_input_dict

# Objects for testing -------------------------------------------------------------------


def the_func_as_i_want_it(a, b: int, c=1):
    return a + b * c


def the_function_as_it_needs_to_be(input_dict: dict):
    # boilerplate, arg! And not even with nice validation etc.
    a = input_dict["a"]
    b = input_dict["b"]
    c = input_dict["c"]
    return a + b * c


# Tests ---------------------------------------------------------------------------------


def test_gather_arguments_into_single_input_dict():
    assert the_func_as_i_want_it(1, 2, 3) == 7
    the_function_as_it_needs_to_be_but_did_not_have_to_write_it_as_such = (
        gather_arguments_into_single_input_dict(the_func_as_i_want_it)
    )

    assert (
        str(
            signature(
                the_function_as_it_needs_to_be_but_did_not_have_to_write_it_as_such
            )
        )
        == "(input_dict: dict)"
    )
    assert (
        the_function_as_it_needs_to_be_but_did_not_have_to_write_it_as_such(
            {"a": 1, "b": 2, "c": 3}
        )
        == 7
    )
    assert (
        the_function_as_it_needs_to_be_but_did_not_have_to_write_it_as_such.__name__
        == "the_func_as_i_want_it"
    )
