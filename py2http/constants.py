"""This module provides functionality for dispatching Python functions as HTTP services. It allows users to create a basic HTTP server from a list of functions or instance methods, customize input and output mapping, handle errors, generate client code from an OpenAPI specification, and configure various aspects of the server setup. The module includes features for transforming class methods, mapping input and output data, handling errors, and generating client code. It also supports configuration options for the HTTP framework, input and output mappers, error handlers, openAPI specifications, logging, middleware, plugins, CORS, SSL certificates, and more."""

JSON_CONTENT_TYPE = "application/json"
BINARY_CONTENT_TYPE = "application/octet-stream"
FORM_CONTENT_TYPE = "multipart/form-data"
RAW_CONTENT_TYPE = "text/plain"
HTML_CONTENT_TYPE = "text/html"

# ``WWW-Authenticate`` challenges sent with every 401 (RFC 7235 requires one): a JWT is
# sent as ``Authorization: Bearer <token>``; an API key as the bare header value.
BEARER_CHALLENGE = "Bearer"
API_KEY_CHALLENGE = "ApiKey"
#: Environment variable naming the challenge for a 401 a dispatched function raised
#: (``AuthorizationError``); the deployment's auth decides it. Default: Bearer.
WWW_AUTHENTICATE_ENV_VAR = "PY2HTTP_WWW_AUTHENTICATE"
#: Set (to anything non-empty) to send an unexpected error's text to the client in a
#: 500 body. Off by default: exception text can carry paths, connection strings or data.
EXPOSE_ERRORS_ENV_VAR = "PY2HTTP_EXPOSE_ERRORS"
#: Legacy switch that forces the generic 500 message (now the default); still honoured.
OPAQUE_ERRORS_ENV_VAR = "OPAQUE_ERRORS"
