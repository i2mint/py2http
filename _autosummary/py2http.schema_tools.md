# py2http.schema_tools

This module provides functions for generating OpenAPI input and output schemas from
Python functions, as well as validating input against a schema.
It also includes a function to create an input mapper based on a transformation
dictionary. The module aims to assist in the generation of API specifications and
input validation for HTTP services built using Python. The functions are designed to
simplify the process of defining API inputs and outputs, and ensuring data integrity
in request handling.

### Functions

| `mk_input_mapper`(transform)                                                            |                                                                        |
|-----------------------------------------------------------------------------------------|------------------------------------------------------------------------|
| [`mk_input_schema_from_func`](#py2http.schema_tools.mk_input_schema_from_func)(func[, ...]) | Make the openAPI input schema for a function.                          |
| `mk_output_schema_from_func`(func)                                                      |                                                                        |
| `mk_sub_dict_schema_from_typed_dict`(typed_dict)                                        |                                                                        |
| `mk_sub_list_schema_from_iterable`(iterable_type)                                       |                                                                        |
| [`param_default`](#py2http.schema_tools.param_default)(param)                   | Return `param.default`, or `Parameter.empty` if it is `i2`'s `NotSet`. |
| `validate_input`(raw_input, schema)                                                     |                                                                        |

### py2http.schema_tools.mk_input_schema_from_func(func, exclude_keys=None, include_func_params=False)

Make the openAPI input schema for a function.

* **Parameters:**
  * **func** – A callable
  * **exclude_keys** – keys to exclude in the schema
  * **include_func_params** – Boolean indicating whether the python Parameter objects should
    also be included (under the field `x-py-param`)
* **Returns:**
  An openAPI input schema dict

```pycon
>>> from py2http.schema_tools import mk_input_schema_from_func
>>> import typing
>>>
>>> def add(a, b: float = 0.0) -> float:
...     '''Adds numbers'''
...     return a + b
...
>>> got = mk_input_schema_from_func(add)
>>> expected = {
...     'type': dict,
...     'properties': {
...         'a': {'type': typing.Any},
...         'b': {'default': 0.0, 'type': float}},
...     'required': ['a']}
>>> assert got == expected, f"\n  expected {expected}\n  got {got}"
>>>
>>>
>>> # TODO: Look into this one: it results in a x default=None (there should be no default)
>>> #       and a type for y (there should be no type, unless by convention)
>>> def mult(x: float, y=1, z: int=1):
...     return (x * y) ** z
...
>>> got = mk_input_schema_from_func(mult)
>>> expected = {
...     'type': dict,
...     'properties': {
...        'x': {'type': float},
...        'y': {'default': 1, 'type': int},
...        'z': {'type': int, 'default': 1}},
...     'required': ['x']}
>>> assert got == expected, f"\n  expected {expected}\n  got {got}"
>>>
>>> # i2's ``NotSet`` sentinel as a default (e.g. in an ``i2.FuncFactory``
>>> # signature) means "no default": the param stays required.
>>> from i2.deco import NotSet
>>> def mult_(x: float = NotSet, y=NotSet, z: int = 1):
...     return (x * y) ** z
>>> mk_input_schema_from_func(mult_) == {
...     'type': dict,
...     'properties': {
...         'x': {'type': float}, 'y': {'type': Any}, 'z': {'type': int, 'default': 1}},
...     'required': ['x', 'y']}
True
```

### py2http.schema_tools.param_default(param)

Return `param.default`, or `Parameter.empty` if it is `i2`’s `NotSet`.

`NotSet` in a signature means “no value given”, not a real default, so schema
builders treat that param as required, with no default (it is not JSON
serializable either).

```pycon
>>> from i2.deco import NotSet
>>> param_default(Parameter('x', Parameter.KEYWORD_ONLY, default=3))
3
>>> param_default(Parameter('x', Parameter.KEYWORD_ONLY, default=NotSet))
<class 'inspect._empty'>
```
