from aiohttp import web
import json
import jwt
from warnings import warn


def mk_jwt_middleware(secret, verify=True):
    @web.middleware
    async def middleware(req, handler):
        auth_header = req.headers.get('Authorization', '')
        token = auth_header[7:]
        try:
            decoded = jwt.decode(token, secret, verify=False)
            req.token = decoded
            return await handler(req)
        except jwt.DecodeError:
            if verify:
                return web.HTTPUnauthorized(text=json.dumps({'error': 'invalid authentication token'}),
                                            content_type='application/json')
            warn(f'Invalid JWT: {token}')
            return await handler(req)

    return middleware


def mk_superadmin_middleware(secret):
    @web.middleware
    async def middleware(req, handler):
        auth_header = req.headers.get('Authorization', '')
        if auth_header == secret:
            return await handler(req)
        return web.HTTPUnauthorized(text=json.dumps({'error': 'invalid API key'}),
                                    content_type='application/json')

    return middleware
