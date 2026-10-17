from uuid import UUID

from fastapi import HTTPException, Request, status
from sqlmodel import select

from app.dependencies import DBSession
from app.models import Admin
from app.services.token import (
    decode_token,
    encode_access_token,
)
from app.settings import settings


def encode_admin_token(admin_uuid: UUID) -> str:
    return encode_access_token(
        {"admin": True, "admin_uuid": str(admin_uuid)},
        expiry_seconds=settings.admin_access_token_ttl_seconds,
    )


def get_current_admin(
    request: Request,
    database_session: DBSession,
) -> Admin:
    from app.settings import settings

    token = request.cookies.get(settings.admin_access_token_name)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication required",
        )

    try:
        payload = decode_token(token)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin session",
        ) from error

    if payload.get("admin") is not True:
        # A well-formed token that is not an admin token: an alum cookie.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This is not an admin session",
        )

    admin_uuid_str: str | None = payload.get("admin_uuid")
    if not admin_uuid_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin session",
        )

    try:
        admin_uuid = UUID(admin_uuid_str)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin session",
        ) from error

    admin = database_session.scalar(
        select(Admin).where(Admin.uuid == admin_uuid, Admin.is_active == True)
    )
    if not admin:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin not found or deactivated",
        )

    return admin
