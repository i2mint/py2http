[Documentation here](https://i2mint.github.io/py2http/)


# py2http
Dispatching Python functions as http services.

You have some python objects and want to get an "equivalent" http service from them...


## Usage

Run a basic HTTP service from a list of functions.
```
from py2http.service import run_app

# Define or import functions
def add(a, b):
    return a + b

def multiply(a, b):
    return a * b

class Divider:
    def __init__(self, dividend):
        self.dividend = divident
    
    def divide(self, divisor):
        return self.dividend / divisor

divider_from_ten = Divider(10)

# Make a list of functions or instance methods
func_list = [add, multiply, divider_from_ten.divide]

# Create an HTTP server
run_app(func_list)
```
The HTTP server will listen on port 3030 by default.
```
# Test the server in a separate process
import requests

url = 'http://localhost:3030/add'
add_args = {'a': 20, 'b': 22}
requests.post(url, json=add_args).json()
# should return 42
```

## Configuration

`run_app` accept many configuration values to customize the handling of HTTP requests and responses. Configuration documentation is listed in the file `config.yaml`.

## Method transformation

Expose class methods by flattening the init -> method call process.

```
from py2http import run_app
from py2http.decorators import mk_flat

class Adder:
    def __init__(self, a):
        self.a = a

    def add(self, b):
        return self.a + b

add = mk_flat(Adder, Adder.add, func_name='add')

func_list = [add]

run_app(func_list)
```

## Input mapping

By default, the server will only accept JSON requests and parse the values from the request body as keyword arguments. You can define custom input mappers to perform extra handling on the JSON body or directly on the HTTP library request object, such as default injection or type mapping.

```
from numpy import array
import soundfile
from py2http.decorators import handle_json_req

from my_service.data import fetch_user_data

@handle_json_req  # extracts the JSON body and passes it to the input mapper as a dict
def array_input_mapper(input_kwargs):
    return {'arr': array(input_kwargs.get('arr', [])),
            'scalar': input_kwargs.get('scalar', 1)}

@handle_multipart_req  # extracts a multipart body and passes it as a dict
def sound_file_input_mapper(input_kwargs):
    file_input = input_kwargs['file_upload']
    filename = file_input.filename
    file_bytes = BytesIO(file_input.file)
    wf, sr = soundfile.read(file_bytes)
    return dict(input_kwargs, wf=wf, sr=sr, filename=filename)

def custom_header_input_mapper(req):  # takes a raw aiohttp request
    user = req.headers.get('User', '')
    return {'user': user}


def array_multiplier(arr, scalar):
    return arr * scalar

def save_audio(wf, sr, filename, storage_path='/audio'):
    target = os.path.join(storage_path, filename)
    soundfile.write(target, wf, sr)

def get_user_data(user):
    return fetch_user_data(user)

array_multiplier.input_mapper = array_input_mapper
save_audio.input_mapper = sound_file_input_mapper
get_user_data.input_mapper = custom_header_input_mapper
```

## Output mapping

By default, the server will send the return value of the handler function in an HTTP response in JSON format. You can define custom output mappers to perform extra handling or type conversion.

```
from io import BytesIO
import soundfile

from py2http.decorators import send_json_resp, send_html_resp

from my_service.data import fetch_blog

@send_json_resp  # sends a JSON response
def array_output_mapper(output, input_kwargs):
    return {'array_value': output['array_value'].tolist()}

@send_html_resp  # sends an HTML response
def mk_html_list(output, input_kwargs):
    tag = input_kwargs.get('tag', 'p')
    item_list = output.split('\n')
    result = [f'<{tag}>{item}</{tag}>' for item in item_list]
    return ''.join(result)

def return_wav(output, input_kwargs):
    wf, sr = output
    wf_bytes = BytesIO()
    soundfile.write(wf_bytes, wf, sr)
    binary_result = wf_bytes.read()
    return web.Response(body=binary_result, content_type='application/octet-stream')


def array_multiplier(arr, scalar):
    return arr * scalar

def get_blog_posts(page):
    return fetch_blog(page)

def download_audio(filename):
    with open(filename) as fp:
        wf, sr = soundfile.read(fp)
    return wf, sr

array_multipler.output_mapper = array_output_mapper

get_blog_posts.output_mapper = mk_html_list

download_audio.output_mapper = return_wav


```

## Error handling

TODO

## Client generation

Py2http generates an OpenAPI specification for the server before running. You can use this document with any OpenAPI-compatible client tools. To extract the specification, you can generate a server application object before running it.
```
import json
from py2http import mk_app, run_app

def add(a, b):
    return a + b

func_list = [add]

app = mk_app(func_list)
openapi_spec = app.openapi_spec

with open('~/openapi.json', 'w') as fp:
    json.dump(openapi_spec, fp)

run_app(app, port=3030)
```

## Configuration

Functions that generate an HTTP service, such as `run_app`, accept a number of keyword arguments for configuration. The available configuration arguments are listed below with their defaults.

* `framework=py2http.config.BOTTLE` The HTTP framework to use.
* `input_mapper=py2http.default_configs.default_input_mapper` A function to map an HTTP request to a dict of input arguments.
* `output_mapper=py2http.default_configs.default_output_mapper` A function to map the output of a function to an HTTP response.
* `error_handler=py2http.default_configs.default_error_handler` A function to map an exception to an HTTP response.
* `header_inputs={}` A dict of object properties in JSON schema format describing keys that should be excluded from request body definitions. These inputs are expected to be extracted from the request headers in the input mapper.
* `protocol='http'` The protocol to include in the OpenAPI specification, either `'http'` or `'https'`
* `host='localhost'` The hostname the server can be reached at, to include in the OpenAPI specification.
* `port=3030` The TCP port to listen on.
* `http_method='post'` The default HTTP method for exposing functions, if a function does not specify its method.
* `openapi={}` A dict with several configuration options specific to the OpenAPI specification, described below.
* `logger=None` An object that implements a `log` method.
* `app_name='HTTP Service'` The name of the application (Flask only).
* `middleware=[]` A list of middlewares to run (aiohttp only).
* `plugins=[]` A list of plugins to install (bottle only).
* `enable_cors=False` Whether to enable CORS features.
* `cors_allowed_origins='*'` If CORS is enabled, the value to pass in the Access-Control-Allow-Origin header.
* `publish_openapi=False` Whether to add a GET /openapi route to the app that returns the OpenAPI specification.
* `openapi_insecure=False` Whether to skip middlewares and plugins for the /openapi route (disabling any authentication).
* `publish_swagger=False` Whether to add a GET route to the app that returns a Swagger HTML interface. 
* `swagger_url='/swagger'` The URL of the swagger route.
* `swagger_title='Swagger'` The title to display on the Swagger HTML page.

OpenAPI configuration:

These values will be put in the OpenAPI specification document. All values are optional.

* `title` The title of the application.
* `version` The version number of the application.
* `auth`: A dict specifying the authentication details to include in the document, to make it easier for clients to automate authentication.
* `auth['auth_type']` Either 'jwt' or 'api_key'.
* `auth['login_details']` A dict describing how a client can log in (for jwt authentication only).
* `auth['login_details']['login_url']` The URL of the login route.
* `auth['login_details']['refresh_url']`: The URL of the refresh route.
* `auth['login_details']['login_inputs']`: A list of strings with the keys expected by the login endpoint.
* `auth['login_details']['refresh_inputs']`: A list of strings with the keys expected by the refresh endpoint.
* `auth['login_details']['outputs']`: A list of strings with the keys returned by the login/refresh endpoints.,
