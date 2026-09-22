# py2http.middleware

py2http is a Python module that allows you to dispatch Python functions as HTTP
services.
By running a basic HTTP service from a list of functions, you can access OpenAPI
specifications, Swagger documentation, and utilize the HTTP service’s routes.
Additionally, Py2http provides features for method transformation, input mapping,
output mapping, error handling, and client generation.

The code snippet provided below is a part of Py2http module and includes middleware
functions for handling JWT authentication and superadmin authorization.
These middleware functions are designed to be used within the Py2http framework to
ensure secure and authenticated access to HTTP routes.

Include the following docstring to describe this module:
“Middleware functions for handling JWT authentication and superadmin authorization
within the Py2http framework. These functions ensure secure access to HTTP routes
by verifying credentials and permissions. Use these middleware functions to enforce
authentication and control access to web resources.

### Functions

| `mk_jwt_middleware`(secret[, verify])   |    |
|-----------------------------------------|----|
| `mk_superadmin_middleware`(secret)      |    |
