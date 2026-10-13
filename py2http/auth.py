"""Framework-independent credential checks, shared by the aiohttp middleware
(``py2http.middleware``) and the Bottle plugins (``py2http.bottle_plugins``), so that
both refuse the same tokens and keys for the same reasons.

>>> bearer_token('Bearer abc'), bearer_token('bearer abc'), bearer_token('Basic abc')
('abc', 'abc', '')
>>> key_matches('k-123', 'k-123'), key_matches('k-12', 'k-123'), key_matches(None, 'k')
(True, False, False)
"""

import hmac
from collections.abc import Iterable

DFLT_JWT_ALGORITHMS = ("HS256",)
_BEARER_PREFIX = "bearer "


class CredentialsRejected(Exception):
    """A request's credentials were refused. The message is safe to show the client:
    it never contains the token, nor anything about the server's key."""


def _algorithm_family(algorithm: str) -> str:
    """The key family an algorithm verifies with: a shared secret for ``HS*``, a
    public key otherwise.

    >>> _algorithm_family('HS512'), _algorithm_family('RS256'), _algorithm_family('ES256')
    ('hmac', 'public-key', 'public-key')
    """
    return "hmac" if algorithm.upper().startswith("HS") else "public-key"


def _names(name: str, value: Iterable[str]) -> list:
    if isinstance(value, (str, bytes)):
        raise TypeError(f"{name} must be a list of names, e.g. [{value!r}]")
    return list(value)


def jwt_algorithms(
    secret,
    *,
    verify: bool = True,
    algorithms: Iterable[str] = DFLT_JWT_ALGORITHMS,
    allow_mixed_algorithm_families: bool = False,
) -> list:
    """Validate a JWT verification setup, returning the algorithms as a list.

    Raises at construction time, rather than accepting forgeries at request time, when:

    - ``algorithms`` is empty, a bare string, or names an unknown or unsigned (``none``)
      algorithm (PyJWT names are case-sensitive);
    - ``verify`` is True and ``secret`` is empty (an empty HMAC secret lets anyone sign
      tokens), or an HMAC algorithm is asked for with a non-``str``/``bytes`` secret;
    - HMAC and public-key algorithms are mixed with one ``secret`` (the classic
      algorithm-confusion setup), unless ``allow_mixed_algorithm_families`` is True.

    >>> jwt_algorithms('s3cret')
    ['HS256']
    >>> jwt_algorithms('', algorithms=['HS256'])
    Traceback (most recent call last):
      ...
    ValueError: secret must be a non-empty key when verify=True
    """
    import jwt

    algorithms = _names("algorithms", algorithms)
    if not algorithms:
        raise ValueError("algorithms must name at least one JWT algorithm")
    known = set(jwt.algorithms.get_default_algorithms()) - {"none"}
    if unknown := [a for a in algorithms if a not in known]:
        raise ValueError(
            f"Unknown or unsigned JWT algorithm(s) {unknown}; names are "
            f"case-sensitive, choose from {sorted(known)}"
        )
    if verify and not secret:
        raise ValueError("secret must be a non-empty key when verify=True")
    families = {_algorithm_family(a) for a in algorithms}
    if verify and "hmac" in families and not isinstance(secret, (str, bytes)):
        raise TypeError(f"an HMAC secret must be str or bytes, got {type(secret)}")
    if len(families) > 1 and not allow_mixed_algorithm_families:
        raise ValueError(
            f"algorithms={algorithms} mixes HMAC and public-key algorithms with one "
            "secret, which allows algorithm-confusion forgeries; use one family, or "
            "pass allow_mixed_algorithm_families=True if you really mean it"
        )
    return algorithms


def bearer_token(authorization_header) -> str:
    """The token of an ``Authorization: Bearer <token>`` header, or ``''``."""
    header = authorization_header or ""
    if header[: len(_BEARER_PREFIX)].lower() != _BEARER_PREFIX:
        return ""
    return header[len(_BEARER_PREFIX) :].strip()


def decode_jwt(token: str, secret, *, algorithms: list, verify: bool = True) -> dict:
    """The claims of ``token``, or ``CredentialsRejected`` with a client-safe reason.

    With ``verify=False`` neither the signature nor the claims (``exp``...) are checked.
    """
    import jwt

    try:
        return jwt.decode(
            token,
            secret,
            options={"verify_signature": verify},
            algorithms=algorithms,
        )
    except jwt.PyJWTError as error:  # incl. a key unfit for the token's alg
        # InvalidTokenError texts describe the token ("Signature has expired"); other
        # PyJWTErrors (InvalidKeyError...) can describe the server's key
        reason = str(error) if isinstance(error, jwt.InvalidTokenError) else None
        raise CredentialsRejected(
            f"Invalid authentication token: {reason or 'not acceptable'}"
        ) from error


def required_key(key, *, name: str = "api_key"):
    """``key``, refused when empty: an empty key would let a request with no
    ``Authorization`` header through."""
    if not key or not isinstance(key, (str, bytes)):
        raise ValueError(f"{name} must be a non-empty str or bytes")
    return key


def key_matches(given, expected) -> bool:
    """Whether the ``given`` credential equals ``expected``, in constant time."""
    if not given or not expected:
        return False

    def _bytes(x):
        return x.encode() if isinstance(x, str) else x

    return hmac.compare_digest(_bytes(given), _bytes(expected))
