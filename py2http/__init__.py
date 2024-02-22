"""This module provides functionality to easily create HTTP services from Python 
functions and class methods. It includes features such as method transformation, 
input mapping, output mapping, error handling, and client generation. 
The module also allows for customization through various configuration options 
and provides the ability to generate OpenAPI specifications for the created HTTP 
services. Additionally, it includes middleware, plugins, and decorators to enhance 
the functionality of the HTTP services."""

from .middleware import mk_jwt_middleware, mk_superadmin_middleware
from .bottle_plugins import JWTPlugin, ApiKeyAuthPlugin
from .service import (
    mk_app,
    run_app,
)
from .decorators import (
    Decorator,
    DecoParam,
    Decora,
    replace_with_params,
    ch_func_to_all_pk,
    mk_flat,
    mk_handlers,
    add_attrs,
)
from .openapi_utils import func_to_openapi_spec
