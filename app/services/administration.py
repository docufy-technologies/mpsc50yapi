"""Admin authentication: its own credential and its own cookie.

An admin token is unusable on alumna routes and vice versa, and the secret is
compared in constant time.
"""

import hmac
from typing import Annotated

from fastapi import Header, HTTPException, Request, status

from app.services.token import decode_token, encode_access_token
from app.settings import settings


def is_valid_admin_secret(secret: str) -> bool:
    """Constant-time comparison of a presented secret against ADMIN_SECRET.

    An unset ADMIN_SECRET fails closed: an unconfigured deployment must never
    accept an empty or missing secret.
    """
    if not settings.admin_secret:
        return False

    return hmac.compare_digest(secret, settings.admin_secret)


def encode_admin_token() -> str:
    # No uuid claim, so this token cannot resolve to an alumna.
    return encode_access_token({"admin": True})


def _read_admin_token(request: Request) -> str | None:
    return request.cookies.get(settings.admin_token_name)


def require_admin(
    request: Request,
    x_admin_secret: Annotated[str | None, Header(alias="X-Admin-Secret")] = None,
) -> None:
    """Authorize an admin request by cookie, falling back to the shared secret.

    The cookie is what the browser panel uses. The `X-Admin-Secret` header is
    kept so `curl` against the API still works without a login.
    """
    if x_admin_secret and is_valid_admin_secret(x_admin_secret):
        return

    token = _read_admin_token(request)
    if token:
        try:
            payload = decode_token(token)
        except Exception as error:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid admin session",
            ) from error

        if payload.get("admin") is True:
            return

        # A well-formed token that is not an admin token: an alumna cookie.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This is not an admin session",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Admin authentication required",
    )