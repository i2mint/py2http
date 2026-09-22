# py2http.route_utils

This module provides functionality to create handlers for class methods,
based on input classes and method names. It also includes a function to generate a
list of handler functions from a class based on a whitelist of method names.

It uses introspection to dynamically create handlers that instantiate the input class
and call the specified method with the provided arguments. The module supports input
and output transformations for the handlers.

You can use this module to easily convert class methods into standalone functions,
which can be useful for creating HTTP services or APIs based on existing class
functionality.

### Functions

| `create_handler`(input_class, methodname)         |    |
|---------------------------------------------------|----|
| `mk_functions_from_class`(input_class, whitelist) |    |
