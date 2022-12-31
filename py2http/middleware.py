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
