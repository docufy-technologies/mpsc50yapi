from datetime import datetime, timedelta
from typing import Any

import jwt
from pydantic.main import BaseModel

from app.helper import now
from app.settings import settings


class TokenPacket(BaseModel):
    token: str
    issued_at: datetime
    expires_at: datetime


def encode_token(data: dict[str, Any], expiry_seconds: int) -> TokenPacket:
    issued_at = now()
    expires_at = issued_at + timedelta(seconds=expiry_seconds)
    iat = int(issued_at.timestamp())
    exp = int(expires_at.timestamp())

    payload: dict[str, Any] = {
        **data,
        "iat": iat,
        "exp": exp,
    }

    token = jwt.encode(
        payload=payload,
        key=settings.jwt_private_key,
        algorithm=settings.jwt_algorithm,
    )

    return TokenPacket(token=token, issued_at=issued_at, expires_at=expires_at)


def decode_token(token: str, verify_exp: bool = True) -> dict[str, Any]:
    return jwt.decode(
        jwt=token,
        key=settings.jwt_public_key,
        algorithms=[settings.jwt_algorithm],
        leeway=30,
        options={"verify_exp": verify_exp},
    )
