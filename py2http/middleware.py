"""
py2http is a Python module that allows you to dispatch Python functions as HTTP 
services. 
By running a basic HTTP service from a list of functions, you can access OpenAPI 
specifications, Swagger documentation, and utilize the HTTP service's routes. 
Additionally, Py2http provides features for method transformation, input mapping, 
output mapping, error handling, and client generation. 

The code snippet provided below is a part of Py2http module and includes middleware 
functions for handling JWT authentication and superadmin authorization. 
These middleware functions are designed to be used within the Py2http framework to 
ensure secure and authenticated access to HTTP routes. 

Include the following docstring to describe this module:
"Middleware functions for handling JWT authentication and superadmin authorization 
within the Py2http framework. These functions ensure secure access to HTTP routes 
by verifying credentials and permissions. Use these middleware functions to enforce 
authentication and control access to web resources.
"""
import json
from warnings import warn
from py2http.constants import JSON_CONTENT_TYPE


def mk_jwt_middleware(secret, verify=True):
    from aiohttp import web
    import jwt

    @web.middleware
    async def middleware(req, handler):
        if handler.__name__ == 'ping' or handler.__name__ == 'openapi':
            return await handler(req)
        auth_header = req.headers.get('Authorization', '')
        token = auth_header[7:]
        try:
            decoded = jwt.decode(
                token, secret, options={'verify': verify}, algorithms=['HS256', 'RS256']
            )
            req.token = decoded
            return await handler(req)
        except jwt.DecodeError as error:
            if verify:
                return web.HTTPUnauthorized(
                    text=json.dumps(
                        {
                            'error': f'Invalid authentication token "{token}", {str(error)}'
                        }
                    ),
                    content_type=JSON_CONTENT_TYPE,
                )
            warn(f'Invalid JWT: {token}')
            return await handler(req)

    return middleware


def mk_superadmin_middleware(secret):
    from aiohttp import web

    @web.middleware
    async def middleware(req, handler):
        auth_header = req.headers.get('Authorization', '')
        if auth_header == secret:
            return await handler(req)
        return web.HTTPUnauthorized(
            text=json.dumps({'error': 'invalid API key'}),
            content_type=JSON_CONTENT_TYPE,
        )

    return middleware
