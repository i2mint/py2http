import requests

add_result = requests.post('http://localhost:3030/add', json={'a': 10, 'b': 5})
print(str(add_result.json()))
multiply_result = requests.post('http://localhost:3030/multiply', json={'multiplier': 6})
print(str(multiply_result.json()))
no_args_result = requests.post('http://localhost:3030/no_args', json={})
print(str(no_args_result.json()))
