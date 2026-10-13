from uuid import UUID

from argon2 import PasswordHasher
from fastapi import HTTPException, Request, status
from sqlmodel import select

from app.database import DBSession
from app.models import Alumna
from app.services.token import decode_token
from app.settings import settings

argon2id_hasher = PasswordHasher()


def hash_password(plain_password: str) -> str:
    return argon2id_hasher.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return argon2id_hasher.verify(hashed_password, plain_password)
    except Exception:
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
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token"
        ) from e


def get_current_alumna(
    request: Request,
    database_session: DBSession,
) -> Alumna:
    """Resolve the cookie to an alumna. Only "cancelled" is rejected, so a
    pending alumna can still reach /payments/* before approval."""
    token = request.cookies.get(settings.access_token_name)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Login Token was not provided",
        )

    uuid = _get_uuid_from_token(token)
    alumna = database_session.scalar(
        select(Alumna).where(Alumna.uuid == uuid, Alumna.status != "cancelled")
    )
    if not alumna:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Alumna not found"
        )

    return alumna
