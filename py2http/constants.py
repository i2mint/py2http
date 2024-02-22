"""This module provides functionality for dispatching Python functions as HTTP services. It allows users to create a basic HTTP server from a list of functions or instance methods, customize input and output mapping, handle errors, generate client code from an OpenAPI specification, and configure various aspects of the server setup. The module includes features for transforming class methods, mapping input and output data, handling errors, and generating client code. It also supports configuration options for the HTTP framework, input and output mappers, error handlers, openAPI specifications, logging, middleware, plugins, CORS, SSL certificates, and more."""
JSON_CONTENT_TYPE = 'application/json'
BINARY_CONTENT_TYPE = 'application/octet-stream'
FORM_CONTENT_TYPE = 'multipart/form-data'
RAW_CONTENT_TYPE = 'text/plain'
HTML_CONTENT_TYPE = 'text/html'
