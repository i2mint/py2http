# py2http.default_configs

This module provides default configurations, input mappers, output mappers,
and error handlers for an HTTP service implemented in Python using the py2http
library. It includes functions for handling JSON requests and responses,
as well as mapping errors to appropriate HTTP responses based on different
HTTP frameworks (AIOHTTP, BOTTLE, FLASK).

The module also defines a set of default configuration values for setting up
the HTTP service, such as the application name, framework to use, port number,
error handling strategy, and CORS settings. It provides flexibility to customize
these configurations based on the specific requirements of the project.

Overall, this module serves as a foundational component for building and setting
up an HTTP service in Python using the py2http library.

### Functions

| `aiohttp_error_handler`(error)             |    |
|--------------------------------------------|----|
| `bottle_error_handler`(error)              |    |
| `bottle_output_mapper`(output, \*\*inputs) |    |
| `default_error_handler`(error)             |    |
| `default_input_mapper`(\*\*inputs)         |    |
| `flask_error_handler`(error)               |    |
| `flask_output_mapper`(output, \*\*inputs)  |    |
