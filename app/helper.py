from datetime import UTC, datetime
from uuid import uuid4

from sqlmodel import Session


def now() -> datetime:
    return datetime.now(UTC)


def generate_reg_code(session: Session) -> str:
    from sqlmodel import select

    from app.models import AlumniProfile

    while True:
        code = uuid4().hex[:12].upper()
        existing = session.scalar(
            select(AlumniProfile).where(AlumniProfile.reg_code == code)
        )
        if not existing:
            return code
