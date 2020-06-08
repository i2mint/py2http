import requests

# import pytest  # TODO: Figure out how to make it a pytest...

add_result = requests.post('http://localhost:3030/add', json={'a': 10, 'b': 5})
assert str(add_result.json()) == '15'
# print(str(add_result.json()))
multiply_result = requests.post('http://localhost:3030/multiply', json={'multiplier': 6})
assert str(multiply_result.json()) == '30'
# print(str(multiply_result.json()))
no_args_result = requests.post('http://localhost:3030/no_args', json={})
assert str(no_args_result.json()) == 'no args'
# print(str(no_args_result.json()))
