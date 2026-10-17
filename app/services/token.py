from datetime import timedelta
from typing import Any

import jwt

from app.helper import now
from app.settings import settings

def encode_access_token(
    data: dict[str, Any], expiry_seconds: int | None = None
) -> str:
    if expiry_seconds is None:
        expiry_seconds = settings.access_token_ttl_seconds
    issued_at = now()
    expires_at = issued_at + timedelta(seconds=expiry_seconds)

    payload: dict[str, Any] = {
        **data,
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    payload.setdefault("type", "access")

    return jwt.encode(
        payload=payload,
        key=settings.jwt_private_key,
        algorithm=settings.jwt_algorithm,
    )


def encode_refresh_token(
    data: dict[str, Any],
    jti: str,
    expiry_seconds: int | None = None,
) -> str:
    if expiry_seconds is None:
        expiry_seconds = settings.alum_refresh_token_ttl_seconds
    issued_at = now()
    expires_at = issued_at + timedelta(seconds=expiry_seconds)

    payload: dict[str, Any] = {
        **data,
        "jti": jti,
        "type": "refresh",
        "iat": int(issued_at.timestamp()),
        "exp": int(expires_at.timestamp()),
    }

    return jwt.encode(
        payload=payload,
        key=settings.jwt_private_key,
        algorithm=settings.jwt_algorithm,
    )


def decode_token(token: str, verify_exp: bool = True) -> dict[str, Any]:
    return jwt.decode(
        jwt=token,
        key=settings.jwt_public_key,
        algorithms=[settings.jwt_algorithm],
        leeway=30,
        options={"verify_exp": verify_exp},
    )


def is_within_refresh_window(payload: dict[str, Any]) -> bool:
    """A token may be refreshed only while it is expired by less than
    REFRESH_WINDOW_SECONDS. Previously this compared `exp` against
    `now - TTL`, which could never trigger before the token was doubly expired."""
    exp_time = payload.get("exp")
    if not isinstance(exp_time, int):
        return False

    return now().timestamp() - exp_time <= REFRESH_WINDOW_SECONDS