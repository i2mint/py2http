# py2http.constants

This module provides functionality for dispatching Python functions as HTTP services. It allows users to create a basic HTTP server from a list of functions or instance methods, customize input and output mapping, handle errors, generate client code from an OpenAPI specification, and configure various aspects of the server setup. The module includes features for transforming class methods, mapping input and output data, handling errors, and generating client code. It also supports configuration options for the HTTP framework, input and output mappers, error handlers, openAPI specifications, logging, middleware, plugins, CORS, SSL certificates, and more.

### Module Attributes

| [`WWW_AUTHENTICATE_ENV_VAR`](#py2http.constants.WWW_AUTHENTICATE_ENV_VAR)   | Environment variable naming the challenge for a 401 a dispatched function raised (`AuthorizationError`); the deployment's auth decides it.   |
|-----------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------|

### py2http.constants.WWW_AUTHENTICATE_ENV_VAR *= 'PY2HTTP_WWW_AUTHENTICATE'*

Environment variable naming the challenge for a 401 a dispatched function raised
(`AuthorizationError`); the deployment’s auth decides it. Default: Bearer.
