from typing import Annotated, Literal
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, HTTPException, Request, status
from sqlmodel import Session, select

from app.database import get_database_session
from app.models import Admin, Alum, RefreshToken
from app.services.token import decode_token, encode_token
from app.settings import settings

argon2id_hasher = PasswordHasher()
# Defined here instead of imported from app.dependencies to avoid the circular
# import (dependencies imports the get_current_* callables from this module).
DBSession = Annotated[Session, Depends(get_database_session)]


def hash_password(plain_password: str) -> str:
    return argon2id_hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return argon2id_hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def encode_alum_access_token(alum: Alum) -> str:
    """Encode an access token for the given alum."""
    return encode_token(
        data={"uuid": str(alum.uuid), "type": "access"},
        expiry_seconds=settings.access_token_ttl_seconds,
    ).token


def encode_alum_refresh_token(alum: Alum) -> tuple[str, RefreshToken]:
    """Encode a refresh token for the given alum."""
    jti = str(uuid4())
    pack = encode_token(
        data={"uuid": str(alum.uuid), "jti": jti, "type": "refresh"},
        expiry_seconds=settings.alum_refresh_token_ttl_seconds,
    )
    return pack.token, RefreshToken(
        created_at=pack.issued_at,
        expires_at=pack.expires_at,
        jti=jti,
        entity_uuid=alum.uuid,
    )


def encode_admin_access_token(admin: Admin) -> str:
    """Encode an access token for the given admin."""
    return encode_token(
        data={"uuid": str(admin.uuid), "type": "access"},
        expiry_seconds=settings.access_token_ttl_seconds,
    ).token


def encode_admin_refresh_token(admin: Admin) -> tuple[str, RefreshToken]:
    """Encode a refresh token for the given admin."""
    jti = str(uuid4())
    pack = encode_token(
        data={"uuid": str(admin.uuid), "jti": jti, "type": "refresh"},
        expiry_seconds=settings.admin_refresh_token_ttl_seconds,
    )
    return pack.token, RefreshToken(
        created_at=pack.issued_at,
        expires_at=pack.expires_at,
        jti=jti,
        entity_uuid=admin.uuid,
    )


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
    token = request.cookies.get(settings.alum_access_token)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Login Token was not provided",
        )
    try:
        payload = decode_token(token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
        ) from e
    token_type = payload.get("type")
    if not token_type or token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type. Expected access token.",
        )
    uuid = _get_uuid_from_token(token)
    alum = database_session.get(Alum, uuid)
    if not alum:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Alum not found"
        )
    if alum.status == "cancelled":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You cannot perform any operation because your account has been cancelled",
        )

    return alum


def get_current_admin(
    request: Request,
    database_session: DBSession,
) -> Admin:
    token = request.cookies.get(settings.admin_access_token)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Login Token was not provided",
        )
    try:
        payload = decode_token(token)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid access token",
        ) from e
    token_type = payload.get("type")
    if not token_type or token_type != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type. Expected access token.",
        )
    uuid = _get_uuid_from_token(token)
    admin = database_session.get(Admin, uuid)
    if not admin or not admin.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Admin not found"
        )

    return admin


def get_refresh_token_record(
    request: Request, database_session: DBSession, entity: Literal["alum", "admin"]
) -> RefreshToken:
    key = (
        settings.alum_refresh_token
        if entity == "alum"
        else settings.admin_refresh_token
    )
    token = request.cookies.get(key)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh Token was not provided",
        )
    try:
        payload = decode_token(token)
        token_type = decode_token(token).get("type")
        if not token_type or token_type != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token type. Expected refresh token.",
            )
        jti: str | None = payload.get("jti")
        if not jti:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Unable to get JTI from token.",
            )
    except HTTPException:
        raise
    except (jwt.InvalidTokenError, ValueError, TypeError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
        ) from e

    refresh_token_record = database_session.scalar(
        select(RefreshToken).where(RefreshToken.jti == jti)
    )
    if not refresh_token_record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Refresh Token record not found",
        )

    return refresh_token_record
