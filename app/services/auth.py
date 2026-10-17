from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import HTTPException, Request, status
from sqlmodel import select

from app.dependencies import DBSession
from app.models import Alum
from app.services.token import decode_token
from app.settings import settings

argon2id_hasher = PasswordHasher()


def hash_password(plain_password: str) -> str:
    return argon2id_hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return argon2id_hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def _get_uuid_from_token(token: str) -> UUID:
    try:
        payload = decode_token(token)
        uuid_str: str | None = payload.get("uuid")
        if not uuid_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unable to get UUID from token.",
            )

        return UUID(uuid_str)
    except HTTPException:
        raise
    except (jwt.InvalidTokenError, ValueError, TypeError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token"
        ) from e


def get_current_alum(
    request: Request,
    database_session: DBSession,
) -> Alum:
    """Resolve the cookie to an alum. Only "cancelled" is rejected, so a
    pending alum can still reach /payments/* before approval."""
    token = request.cookies.get(settings.access_token_name)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Login Token was not provided",
        )

    uuid = _get_uuid_from_token(token)
    alum = database_session.scalar(
        select(Alum).where(Alum.uuid == uuid, Alum.status != "cancelled")
    )
    if not alum:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Alum not found"
        )

    return alum
